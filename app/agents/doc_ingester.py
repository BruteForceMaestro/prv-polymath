# ingests markdown directly (but with a limit on how huge the ingested markdown can be)
from app.tracing import traced
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.ui import Console
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import FunctionCallTermination
from app.config import budget_model_client
from app.work import AgentWork
from app.graphtools import invoke_axiom, imply_new, graph_search

doc_ingester_sys = """
You are a researcher-mapper, engaging with papers and mathematical literature to map statements
and implications in the arguments to a graph scaffolding, with Statements (Axioms, Theorems, Definitions, Lemmas)
as nodes and Implications as edges.

# Tools
## Observing
1. `graph_search`: performs a vector search for a statement or implication with a vector representation of the query. 
Use to find already existing nodes to possibly connect to, so you don't create duplicates of nodes.
## Mapping
You have the following tools to map the mathematical document onto the graph.
1. `invoke_axiom`: add a statement to the graph which has no proof and is assumed to be true - use for standard
results in the literature or statements from papers published. 
2. `imply_new`: from previous statements, imply a new statement, via some tactic or mechanism. 
Use when following a logical chain estabilished in the document.
## Finalizing
When you have mapped all of the argument(s) established in the provided text, call the 
`submit_answer` tool to finalize the mapping process.

"""

@traced
async def ingest_document(doc_text: str):
    """Uses an AI agent to ingest a document (typically MD after conversion by Datalab) 
    and output a list of nodes and implications in the database (actually a list of logical chains)
    with a verification level determining the level of trust in something.
    """
    work = AgentWork()
    agent = AssistantAgent(
        name="Doc_Ingester",
        model_client=budget_model_client,
        system_message=doc_ingester_sys,
        tools=[graph_search, invoke_axiom, imply_new, work.submit_answer]
    )

    team = RoundRobinGroupChat(
        [agent],
        termination_condition=FunctionCallTermination("submit_answer")
    )

    await Console(team.run_stream(task=f"Map the following literature to the graph: <literature>{doc_text}</literature>"))

    return work.result
