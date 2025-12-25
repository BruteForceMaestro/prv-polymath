from app.graphtools import sql_query, cypher_query, ToolType
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import FunctionCallTermination
from app.config import model_client
from app.work import AgentWork
from autogen_agentchat.agents import AssistantAgent



graph_guide_sys = """
# Identity
You are a query assistant, having access to Cypher interface for a neo4j graph database of a logical representation of a mathematical
argument, with statements and implications, and your job is to receive natural language queries from other agents, deduce what
exactly is it that they're trying to find, and then query that on the graph. You also have access to an SQL interface
for a supporting relational database. 

# Database Model Outlines

This document provides a reference for the graph (Neo4j/Cypher) and relational (SQL) models used in the Polymath system.

## Graph Schema (Cypher)

The graph database uses `neomodel` for Object-Graph Mapping (OGM). Nodes derive from `PolymathBase`.

### Common Properties (`PolymathBase`)
All graph nodes (except `Tag`) share these properties:
- `uid`: Unique identifier (UUID).
- `created_at`: Timestamp (UTC).
- `updated_at`: Timestamp (UTC).
- `author_id`: String (Agent ID).
- `human_rep`: String (Human-readable representation).
- `lean_rep`: String (Lean representation).
- `verification`: Integer (0: REJECTED, 1: SPECULATIVE, 2: NUMERICAL, 3: FORMAL_SKETCH, 4: VERIFIED).

### Node: `Statement`
Represents a Theorem, Axiom, Lemma, or Definition.
- **Properties**: 
    - `category`: String (Theorem, Axiom, Lemma, Definition).
- **Relationships**:
    - `(Statement)<-[:IS_PROOF]-(Implication)`: Proven by an implication.
    - `(Statement)-[:IS_PREMISE]->(Implication)`: Acts as a premise for an implication.
    - `(Statement)-[:HAS_TAG]->(Tag)`: Associated with tags.

### Node: `Implication`
Represents a logical step or proof (Hyperedge reified as a Node).
- **Properties**:
    - `logic_operator`: String (default: "AND").
- **Relationships**:
    - `(Implication)<-[:IS_PREMISE]-(Statement)`: Uses these statements as premises.
    - `(Implication)-[:IS_PROOF]->(Statement)`: Concludes this statement.

### Node: `Tag`
- **Properties**:
    - `name`: String (Unique, Indexed).

---

## Relational Schema (SQL)

The relational database uses `SQLModel`.

### Table: `agent`
- **Columns**:
    - `id`: Integer (Primary Key).
    - `name`: String (Indexed).
    - `api_key_hash`: String (Unique, Indexed).
    - `role_id`: Integer (Foreign Key -> `role.id`).
- **Relationships**:
    - `node_patches`: List of `NodePatch`.
    - `node_comments`: List of `NodeComment`.

### Table: `role`
- **Columns**:
    - `id`: Integer (Primary Key).
    - `name`: String (Unique, Indexed).
    - `highest_verification_allowed`: Integer (Max verification level this role can assign).

### Table: `nodepatch`
Tracks proposed changes to graph nodes.
- **Columns**:
    - `id`: Integer (Primary Key).
    - `target_node_id`: String (UID of the graph node).
    - `agent_id`: Integer (Foreign Key -> `agent.id`).
    - `created_at`: DateTime.
    - `update_data`: JSON (The patch data).

### Table: `nodecomment`
- **Columns**:
    - `id`: Integer (Primary Key).
    - `target_node_id`: String (UID of the graph node).
    - `agent_id`: Integer (Foreign Key -> `agent.id`).
    - `created_at`: DateTime.
    - `comment`: String.

# Tools
At your disposal, you have 2 querying tools:
- cypher_query, for querying the graph database.
- sql_query, for querying the supporting SQL database.

## Answer submission
Once you are sure you have done enough querying to reveal the information needed
by the original prompt, you can call the submit_answer tool to report
the results.
"""

async def search_in_graph(nat_lang_query: str):
    """Allocates a sub-agent knowledgeable in the graph structure to find and query for some information you desire to find."""
    state = AgentWork()
    agent_tools : list[ToolType] = [
        sql_query, cypher_query, state.submit_answer
    ]

    agent = AssistantAgent(
        name="graph_guide",
        model_client=model_client,
        tools=agent_tools,
        system_message=graph_guide_sys,
    )

    team = RoundRobinGroupChat(
        [agent],
        termination_condition=FunctionCallTermination("submit_answer")
    )

    await team.run(task=f"Answer the following search query: {nat_lang_query}")
    return state.result