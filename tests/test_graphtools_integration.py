import pytest
import requests
import asyncio
from app.graphtools import (
    observe_graph,
    get_node_info,
    invoke_axiom,
    imply_new,
    patch_node,
    comment_node,
    cypher_query,
    sql_query
)
from polymath_schemas.graph import VerificationLevel
from polymath_schemas.api_requests import NodePatchRequest
from app.config import POLYMATH_SERVER_URL

@pytest.mark.asyncio
async def test_backend_connection():
    """Verify that the backend is actually reachable."""
    try:
        # requests is sync
        response = requests.get(f"{POLYMATH_SERVER_URL}/docs")
        assert response.status_code == 200
    except Exception as e:
        pytest.fail(f"Backend at {POLYMATH_SERVER_URL} is not reachable: {e}")

@pytest.mark.asyncio
async def test_observe_graph_integration():
    # Treating as sync because they are defined with 'def', not 'async def'.
    # The @traced decorator preserves synchronicity.
    result = observe_graph()
    assert isinstance(result, dict)

@pytest.mark.asyncio
async def test_cypher_query_integration():
    query = "MATCH (n) RETURN count(n) as count"
    result = cypher_query(query)
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_sql_query_integration():
    query = "SELECT 1"
    result = sql_query(query)
    print(result)
    assert isinstance(result, dict)
    assert result is not None

@pytest.mark.asyncio
async def test_axiom_lifecycle_integration():
    human_rep = f"Test Axiom {VerificationLevel.VERIFIED}"
    lean_rep = "theorem test : True := trivial"
    
    create_result = invoke_axiom(lean_rep, human_rep)
    assert isinstance(create_result, dict)
    
    assert "uid" in create_result
    node_id = create_result["uid"]
    
    node_info = get_node_info(node_id)
    assert isinstance(node_info, dict)

@pytest.mark.asyncio
async def test_comment_integration():
    create_result = invoke_axiom("theorem test_comment : True := trivial", "Comment Test Node")
    assert isinstance(create_result, dict)
    node_id = create_result["uid"]
    
    comment_text = "This is a test comment"
    comment_result = comment_node(comment_text, node_id)
    assert isinstance(comment_result, dict)
    
    node_info = get_node_info(node_id)
    assert isinstance(node_info, dict)

@pytest.mark.asyncio
async def test_patch_node_integration():
    create_result = invoke_axiom("theorem test_patch : True := trivial", "Original Rep")
    assert isinstance(create_result, dict)
    node_id = create_result["uid"]
    
    patch_data = NodePatchRequest(human_rep="Updated Rep")
    patch_result = patch_node(patch_data, node_id)
    assert isinstance(patch_result, dict)
    
    node_info = get_node_info(node_id)
    assert isinstance(node_info, dict)
