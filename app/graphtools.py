import requests
from app.config import POLYMATH_SERVER_URL, POLYMATH_API_KEY
from polymath_schemas.graph import VerificationLevel
from polymath_schemas.api_requests import CreateStatement, CreateImplication, NodePatchRequest
from polymath_schemas.api_responses import StatementRead
from autogen_core.tools._base import BaseTool
from typing import Union, Callable, Awaitable, Literal, Any

ToolType = Union[Callable[..., Awaitable[Any]], Callable[..., Any], BaseTool[Any, Any]]

def make_graph_request(endpoint: str, body: Any = None, method: str = "POST"):
    try:
        headers = {
            "X-API-Key": POLYMATH_API_KEY,
            "Content-Type": "application/json"
        }
        if not body:
            response = requests.get(
                POLYMATH_SERVER_URL + endpoint,
                headers=headers
            )
        elif method == "PATCH":
            response = requests.patch(
                POLYMATH_SERVER_URL + endpoint,
                json=body,
                headers=headers
            )
        else:
            response = requests.post(
                POLYMATH_SERVER_URL + endpoint,
                json=body,
                headers=headers
            )
        response.raise_for_status()
    except Exception as e:
        return f"Exception in making graph request: {e}"
    
    return response.json()

def observe_graph():
    """Provide a big picture view of the state of the art - the numerically or formally verified statements."""
    cypher_q = """
    MATCH (conclusion:Statement)
    WHERE conclusion.verification >= 2

    RETURN conclusion
    """
    return make_graph_request(
        endpoint="/graph/query",
        body=cypher_q
    )

def get_node_info(node_id: str):
    """Get deeper information (history of changes, comment discussions, connected nodes) about a node."""
    return make_graph_request(
        endpoint=f"/graph/nodes/{node_id}"
    )

def invoke_axiom(lean_rep: str, human_rep: str):
    """Add a statement node to the graph, that is verified, and that has no supporting premises. 
    Used for commonly used, widely known results. 
    """
    post_stmt = CreateStatement(
        human_rep=human_rep,
        lean_rep=lean_rep,
        category="Axiom",
        verification=VerificationLevel.VERIFIED,
        tags=["literature"]
    )
    return make_graph_request(
        endpoint="/graph/nodes/statement",
        body=post_stmt.model_dump()
    )

def imply_new(
    premises_ids: list[str], 
    new_stmt_human: str,
    tactic_human: str, # how was the new stmt obtained
    new_stmt_lean: str, 
    tactic_lean: str,
    logic_op: Literal['OR', 'AND'] = "AND",
    category: Literal['Theorem', 'Axiom', 'Definition', 'Lemma'] = "Lemma"
):
    """
    Implies new statement given previously established statements.
    Requires a representation of the new statement in both human-readable LaTeX and Lean.
    Requires a representation of the tactic (how was the new statement obtained?) in both human-readable LaTeX and Lean. 
    """

    cypher_q = """
    MATCH (s:Statement)
    WHERE s.uid IN $ids
    RETURN s.uid AS uid, s.verification AS verification
    """
    result = make_graph_request(
        endpoint="/graph/query",
        body=cypher_q.replace("$ids", str(premises_ids)) # DEFINITELY inSECURE
    )
    if result.startswith("Exception"):
        # yeah, these premises ids not found
        return "Premises IDs are invalid / not found in the graph."
    
    # create a statement
    new_stmt = CreateStatement(
        human_rep=new_stmt_human,
        lean_rep=new_stmt_lean,
        verification=VerificationLevel.SPECULATIVE,
        category=category
    )

    filled_stmt = StatementRead.model_validate_json(
        make_graph_request(
            endpoint="/graph/nodes/statement",
            body=new_stmt.model_dump()
        )
    )

    # create an implication
    new_impl = CreateImplication(
        human_rep=tactic_human,
        lean_rep=tactic_lean,
        premises_ids=premises_ids,
        concludes_ids=filled_stmt.uid,
        verification=VerificationLevel.SPECULATIVE,
        logic_op=logic_op
    )

    return make_graph_request(
        endpoint="/graph/nodes/implication",
        body=new_impl.model_dump()
    )

def patch_node(patch: NodePatchRequest, node_id: str):
    """Make an edit to an existing node."""
    return make_graph_request(
        endpoint=f"/graph/nodes/{node_id}",
        body=patch.model_dump(),
        method="PATCH"
    )

def comment_node(comment: str, node_id: str):
    """Comment on a node to detail your work done, results, approaches tried, so forth."""
    return make_graph_request(
        endpoint=f"/graph/nodes/{node_id}/comment",
        body=comment
    )

def cypher_query(cypher_q: str):
    """Cypher query interface for the graph database."""
    return make_graph_request(
        endpoint=f"/graph/query",
        body=cypher_q
    )

def sql_query(sql_q: str):
    """SQL query interface for the SQL database."""
    return make_graph_request(
        endpoint=f"/metadata/query",
        body=sql_q
    )