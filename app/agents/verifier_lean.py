# autogen
from kimina_client.models import Snippet
from kimina_client import Infotree
from app.utils.infotree import extract_data
from autogen_agentchat.ui import Console
from app.config import model_client
from app.work import AgentWork
from app.agents.deterministic_nudger import DeterministicNudgeAgent
from app.groupchats.nudge import NudgeGroupChat
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import FunctionCallTermination
from kimina_client import AsyncKiminaClient
import uuid
from dataclasses import dataclass


client = AsyncKiminaClient(
    api_url="http://localhost:8081"
)


@dataclass(frozen=True)
class SplitSnippet:
    header: str
    body: str
    header_line_count: int

# i couldn't figure out the import so i just copied the code lol
def split_snippet(code: str) -> SplitSnippet:
    """
    Splits a code snippet into a header (imports) and body.

    - Header: all lines at the top that are 'import ...' or blank before the first non-import line.
      If any import starts with 'import Mathlib', include a single 'import Mathlib' at the top of the header.
      Other imports follow in their original order, without duplicates.
    - Body: the rest of the code starting from the first non-import/non-blank line.
    """
    lines = code.splitlines()

    # Separate header from body
    i = 0
    while i < len(lines) and (
        lines[i].strip() == "" or lines[i].strip().startswith("import ")
    ):
        i += 1
    header_lines = [x.strip() for x in lines[:i]]
    body = "\n".join(lines[i:])

    # Process imports in header
    import_lines = [line for line in header_lines if line.startswith("import ")]
    imports: list[str] = []
    seen: set[str] = set()
    has_mathlib = False
    for line in import_lines:
        if line.startswith("import Mathlib"):
            has_mathlib = True
        else:
            if line not in seen:
                seen.add(line)
                imports.append(line)

    # Build final header
    result_header: list[str] = []
    if has_mathlib:
        result_header.append("import Mathlib")
    result_header.extend(imports)

    header = "\n".join(result_header)
    return SplitSnippet(header=header, body=body, header_line_count=i)


async def lean_tool(lean_code: str) -> str | list:
    """
    Execute a Lean 4 command or tactic. 
    Returns the new goal state or errors.
    Use this to prove theorems step-by-step.
    """
    serv_check = await client.check(
        Snippet(id=str(uuid.uuid4()), code=lean_code),
        timeout=600, infotree=Infotree.tactics
    )

    if not serv_check.results[0].response:
        return "No response returned"
    infotree = serv_check.results[0].response["infotree"]
    snip = split_snippet(lean_code)
    intervals = extract_data(infotree, snip.body)

    return intervals

lean_verifier_sys = """You are a formal verification expert in Lean 4. 
You have access to a persistent Lean REPL.
1. Declare theorems using 'theorem name ...'
2. Prove them step-by-step.
3. If you get an error, read it and correct your tactic.
4. When the goal is empty, the proof is complete.

Then, when your proving process concludes (either success or failure), call the 
`submit_answer` tool to report your findings, with a stated reason to the outcome.
"""

async def verify_lean(lean_task: str, context: str, work: AgentWork):
    """Allocates a sub-agent to attempt to verify things formally with Lean theorem prover.
    The verifier agent does not have your context or access to the graph, so provide it 
    (definitions, lemmas or statements necessary, etc.) along with the task.
    """
    agent = AssistantAgent(
        name="lean_verifier",
        system_message=lean_verifier_sys,
        model_client=model_client,
        tools=[lean_tool, work.submit_answer],
    )

    nudger = DeterministicNudgeAgent(
        name="nudge_agent",
        message_content="You seem to be looping. You can use `submit_answer` if the task is completed or can't be completed."
    )

    team = NudgeGroupChat(
        [agent, nudger],
        termination_condition=FunctionCallTermination("submit_answer")
    )

    run_task = f"Given the following context: <context>{context}</context>\n\n Complete the following task: <current_goal>{lean_task}</current_goal>"

    await work.log_stream(team.run_stream(task=run_task))
    return work.result