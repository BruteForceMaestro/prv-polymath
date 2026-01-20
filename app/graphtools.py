import requests
from app.config import POLYMATH_SERVER_URL, POLYMATH_API_KEY
from polymath_schemas.graph import VerificationLevel
from polymath_schemas.api_requests import CreateStatement, CreateImplication, NodePatchRequest
from polymath_schemas.api_responses import StatementRead
from autogen_core.tools._base import BaseTool
from typing import Union, Callable, Awaitable, Literal, Any, Optional

ToolType = Union[Callable[..., Awaitable[Any]], Callable[..., Any], BaseTool[Any, Any]]

def make_graph_request(endpoint: str, body: Any = None, method: str = "POST") -> dict | str:
    response = None
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
        detail = "Detail not provided"
        if response is not None:
            # Check if the response is actually JSON before parsing
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                try:
                    detail = response.json()
                except ValueError:
                    detail = response.text
            else:
                detail = response.text # Return raw HTML/Text if not JSON
        
        return f"Exception in making graph request: {e},\n\n Detail: {detail}"
    
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

def invoke_axiom(snake_case_id: str, lean_rep: str, human_rep: str):
    """Add a statement node to the graph, that is verified, and that has no supporting premises. 
    Used for commonly used, widely known results. Both human and lean (formal) representations.
    Title of the axiom, short, in snake_case.
    """
    post_stmt = CreateStatement(
        uid=snake_case_id,
        human_rep=human_rep,
        lean_rep=lean_rep,
        category="Axiom",
        verification=int(VerificationLevel.VERIFIED),
        tags=["literature"]
    )
    return make_graph_request(
        endpoint="/graph/nodes/statement",
        body=post_stmt.model_dump()
    )

def imply_new(
    premises_ids: list[str], 
    new_stmt_snake_case_id: str,
    new_stmt_human: str,
    tactic_human: str, # how was the new stmt obtained
    new_stmt_lean: Optional[str], 
    tactic_lean: Optional[str],
    logic_op: Literal['OR', 'AND'] = "AND",
    category: Literal['Theorem', 'Axiom', 'Definition', 'Lemma'] = "Lemma"
):
    """
    Implies new statement given previously established statements (not Implications).
    Requires a representation of the new statement in both human-readable LaTeX and Lean. Applies a unique id to the 
    new statement in snake_case, for database retrieval.
    Requires a representation of the tactic (how was the new statement obtained?) in both human-readable LaTeX and Lean. 
    """

    if len(premises_ids) == 0:
        return "You have to imply the statement from some other statement. Invoke an axiom if you need a base statement."

    cypher_q = """
    MATCH (s:Statement)
    WHERE s.uid IN $ids
    RETURN s.uid AS uid, s.verification AS verification
    """
    result = make_graph_request(
        endpoint="/graph/query",
        body=cypher_q.replace("$ids", str(premises_ids)) # DEFINITELY inSECURE
    )
    assert isinstance(result, dict) # not an error
    if result['count'] == 0:
        # none found as premises. 
        return "There are no STATEMENTs with the premises ids provided. Maybe you tried to imply with an implication as premise but that's not allowed."
    # create a statement
    new_stmt = CreateStatement(
        uid=new_stmt_snake_case_id,
        human_rep=new_stmt_human,
        lean_rep=new_stmt_lean or "No Lean representation available.",
        verification=int(VerificationLevel.SPECULATIVE),
        category=category
    )
    resp = make_graph_request(
            endpoint="/graph/nodes/statement",
            body=new_stmt.model_dump()
    )
    if isinstance(resp, str):
        raise Exception(resp)

    filled_stmt = StatementRead.model_validate(resp)

    # try to autogenerate title for the implication with ids
    new_impl_uid = f"if_{f"_{logic_op}_".join(premises_ids)}_then_{filled_stmt.uid}"
    # create an implication
    new_impl = CreateImplication(
        uid=new_impl_uid,
        human_rep=tactic_human,
        lean_rep=tactic_lean or "No Lean representation avaliable.",
        premises_ids=premises_ids,
        concludes_ids=[filled_stmt.uid],
        verification=int(VerificationLevel.SPECULATIVE),
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
        endpoint=f"/graph/metadata/query",
        body=sql_q
    )

def graph_search(human_rep: str):
    """Semantic search (dense vector embeddings)
     on the Implications or Statements' human (natural language, LaTeX) representations.
    """
    return make_graph_request(
        endpoint=f"/graph/vector_query",
        body=human_rep
    )