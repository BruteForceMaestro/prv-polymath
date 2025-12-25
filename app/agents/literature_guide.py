from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import FunctionCallTermination
from app.config import model_client
from autogen_agentchat.agents import AssistantAgent
from autogen_ext.agents.web_surfer import MultimodalWebSurfer
from app.work import AgentWork


literature_agent_sys = """
# Identity
You are a literature review agent. You are tasked with finding reputable sources, such as journal articles or 
books or other kinds of academic/well-respected literature on the topic of assignment. 

# Capabilities
You are in a round-robin group chat interaction with an agent which has multi-modal access to the Internet,
including arXiv and the otehr sourecs you would need.

# Final answer
When you are have found sufficient information to give an answer to the original query,
use the submit_answer tool. 
""".strip()

async def research_literature(task: str):
    """Allocates a sub-agent to researching literature (arXiV, papers, books) on a topic, to come back with a detailed report."""

    state = AgentWork()
    web_surfer = MultimodalWebSurfer(
        name="Web_Surfer",
        model_client=model_client,
        headless=False,  # Set to False to watch it browse (useful for debugging)
    )

    literature_researcher = AssistantAgent(
        name="literature_guide",
        model_client=model_client,
        system_message=literature_agent_sys,
        tools=[state.submit_answer]
    )

    team = RoundRobinGroupChat(
        [literature_researcher, web_surfer],
        termination_condition=FunctionCallTermination("submit_answer")
    )

    await team.run(task=task)

    return state.result
