from app.agents.verifier_numeric import NumericVerifierWork
from app.graphtools import graph_search
from app.graphtools import imply_new
from app.graphtools import observe_graph
from app.graphtools import *
from app.groupchats.nudge import NudgeGroupChat
from app.agents.deterministic_nudger import DeterministicNudgeAgent
from autogen_agentchat.conditions import FunctionCallTermination
from app.config import model_client
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.ui import Console
from app.agents.literature_suggester import suggest_literature
from app.agents.verifier_numeric import verify_numeric
from app.agents.verifier_lean import verify_lean
from app.work import AgentWork
import asyncio


researcher_sys = """# Identity
You are a brilliant Researcher in mathematics, having access to a mathematical graph of Statements and Implications
as scaffolding.

# Capabilities
## Direct graph interaction
You can edit/view the graph directly via the tools at your disposal: `graph_search`,
`get_node_info`, `invoke_axiom`, `imply_new`, `patch_node`, `comment_node`. Here, node refers both
to statements and implications. Always store as much of your work as possible in graph
form.

## Sub-agent orchestration
You can invoke sub-agents with tool calls. At your disposal:
1. Numeric/Symbolic Verifier Agent (via `verify_numeric`) - use when needing to verify an implication 
or other equivalence. Agent will have SymPy and other Python tools at disposal, so tailor your tasks
to this agent with this in mind. If approval of this agent is gained, you may raise verification level
of nodes to 2 or 3.
2. Lean Verifier Agent (via `verify_lean`) - use when needing to formally prove an implication or equivalence.
Agent has a Lean REPL at disposal, so tailor your task to this agent to be more Lean specific. If approval of this
agent is gained, you may raise verification level of nodes to 4.

# Task Workflow
Working with a mathematical graph, you can build a logical chain of Statements and Implications using your tools,
representing your argument, however, they will all begin with verification level 1 (speculative). Verification levels
are 0 (Rejected), 1 (Speculative), 2 (Numeric), 3 (Formal Sketch), 4 (Formal Proof, Lean 4 verified). Verify each Implication in
your argument, and then patch that node to reflect the new verification level, without this, the proof will be considered
incomplete. The goal is to have each step in your chain verified formally with Lean 4, but numeric or symbolic verification
 can also be acceptable under certain circumstances.

# Answer submission
When you have completed your assignment with a very high degree of confidence, or failed to do so and deem
the task impossible with your capabilities, you can use the `submit_answer` tool to provide an in-depth
report on your progress.
"""


class ResearcherWork(AgentWork):
    recursive_depth: int = 0
async def assign_researcher(task: str, work: ResearcherWork):
    """Allocates a researcher sub-agent, with similar capabiliites, to a more specialized task."""
    if work.recursive_depth > 10:
        raise Exception("Agents too far down be like")

    async def _verify_lean(task: str):
        """Allocates a sub-agent with a Lean 4 REPL to verify formal statements rigorously."""
        new_func = work.get_subagent_func(verify_lean, AgentWork)
        return await new_func(lean_task=task)
    
    async def _verify_numeric(task: str):
        """Allocates a sub-agent with a SymPy/python environment to verify symbolic manipulations or provide numeric verification."""
        new_func = work.get_subagent_func(verify_numeric, NumericVerifierWork)
        return await new_func(task=task)
    
    researcher_tools : list[ToolType] = [
        get_node_info, invoke_axiom, imply_new, patch_node, comment_node,
        graph_search, _verify_lean, _verify_numeric, 
        work.submit_answer,
        #  suggest_literature, observe_graph, tracker.divide_and_conquer,
    ]

    print(researcher_tools)

    researcher_agent = AssistantAgent(
        name="researcher",
        model_client=model_client,
        tools=researcher_tools,
        system_message=researcher_sys
    )

    nudge_agent = DeterministicNudgeAgent(
        name="nudge_asgent",
        message_content="You seem to be looping. Please evaluate your progress and use the 'submit_answer' tool if you are finished."
    )

    termination_con = FunctionCallTermination(
        function_name="submit_answer"
    )

    team = NudgeGroupChat(
        participants=[researcher_agent, nudge_agent],
        termination_condition=termination_con
    )

    await work.log_stream(team.run_stream(task=task))
    return work.result
