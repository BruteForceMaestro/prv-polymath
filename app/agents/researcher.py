from app.graphtools import imply_new
from app.tracing import traced
from app.graphtools import observe_graph
from app.graphtools import *
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import FunctionCallTermination
from app.config import model_client
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.ui import Console
from app.agents.graph_guide import search_in_graph
from app.agents.literature_guide import research_literature
from app.agents.verifier_numeric import verify_numeric
from app.agents.verifier_lean import verify_lean
from app.work import AgentWork
import asyncio


researcher_sys = """# Identity
You are a brilliant Researcher in mathematics, collaborating with other Agents and Researchers in a hierarchical
structure to solve complex problems with formal/numerical/symbolic verification of steps. All of Researchers share
a logical graph scaffolding with Statements and Implications, where everyone's progress is shared and stored.

# Capabilities
## Direct graph interaction
You can edit/view the graph directly via the tools at your disposal: observe_graph,
get_node_info, invoke_axiom, imply_new, patch_node, comment_node. Here, node refers both
to statements and implications. Always store as much of your work as possible in graph
form.

## Sub-agent orchestration
You can invoke sub-agents with tool calls. Always consider that you're operating with
a team. At your disposal:
1. Query Agent (via search_in_graph) - use when needing a complex/multi-step query or data retrieval from
the graph or database, it is trained with the database schemas to make proper queries. You 
should pass in natural language instructions on what you need to retrieve.
2. Literature Agent (via research_literature) - use when needing to retrieve information from
the field (papers, resources, arXiV) about a problem, suggesting approaches that have been used for similar
problems in the past. 
3. Numeric/Symbolic Verifier Agent (via verify_numeric) - use when needing to verify an implication 
or other equivalence. Agent will have SymPy and other Python tools at disposal, so tailor your tasks
to this agent with this in mind. If approval of this agent is gained, you may raise verification level
of nodes to 2 or 3.
4. Lean Verifier Agent (via verify_lean) - use when needing to formally prove an implication or equivalence.
Agent has a Lean REPL at disposal, so tailor your task to this agent to be more Lean specific. If approval of this
agent is gained, you may raise verification level of nodes to 4.
5. Sub-researcher Agent Team (via divide_and_conquer) - use if needing to "divide and conquer", assigning more
specialized parts of the problem to different sub-researcher agents (having the same capabilities as you),
if the problem is sufficiently complex. 

# Answer submission
When you have completed your assignment with a very high degree of confidence, or failed to do so and deem
the task impossible with your capabilities, you can use the submit_answer tool to provide an in-depth
report on your progress.
"""


class ResearcherWork(AgentWork):
    def __init__(self):
        super().__init__()
        self.recursive_depth = 0
    
    async def divide_and_conquer(self, tasks: list[str]):
        """Allocate a parallel-running team of sub-researcher agents to tackle smaller, less-complex tasks."""
        return await asyncio.gather(*[assign_researcher(task, self.recursive_depth+1) for task in tasks])
        

@traced
async def assign_researcher(task: str, recursive_depth=0):
    """Allocates a researcher sub-agent, with similar capabiliites, to a more specialized task."""
    tracker = ResearcherWork()
    tracker.recursive_depth = recursive_depth

    if recursive_depth > 10:
        raise Exception("Agents too far down be like")
    
    researcher_tools : list[ToolType] = [
        observe_graph, get_node_info, invoke_axiom, imply_new, patch_node, comment_node,
        search_in_graph, research_literature, verify_lean, verify_numeric, tracker.divide_and_conquer,
        tracker.submit_answer
    ]

    researcher_agent = AssistantAgent(
        name="researcher",
        model_client=model_client,
        tools=researcher_tools,
        system_message=researcher_sys
    )

    termination_con = FunctionCallTermination(
        function_name="submit_answer"
    )

    team = RoundRobinGroupChat(
        participants=[researcher_agent],
        termination_condition=termination_con
    )

    await Console(team.run_stream(task=task))
    return tracker.result
