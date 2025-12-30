from fastapi.testclient import TestClient
from app.main import app
import time
import json

problem = """
Let $m_0$ and $n_0$ be distinct positive integers. For every positive integer $k$,
define $m_k$ and $n_k$ to be the relatively prime positive integers such that
\\[
\\frac{m_k}{n_k} = \\frac{2m_{k-1} + 1}{2n_{k-1}+1}.
\\]
Prove that $2m_k+1$ and $2n_k+1$ are relatively prime for all but finitely many positive integers $k$.
"""

def research_solve_problem():
    client = TestClient(app)
    response = client.post("/set_problem", json={"problem": problem, "use_lit_review": False})
    assert response.status_code == 200
    data = response.json()
    print(f"Response: {data}")
    assert "status" in data
    assert data["status"] == "ok"
    # This assertion is expected to fail before implementation
    assert "trace_id" in data
    assert isinstance(data["trace_id"], str)
    assert len(data["trace_id"]) > 0

    time.sleep(10)
    # then query that
    response = client.get(f"/trace/{data['trace_id']}")
    data = json.loads(response.json())

    with open('traced_log.json', 'w') as f:
        json.dump(data, f, indent=4, sort_keys=True)

def get_trace(trace_id: str):

    client = TestClient(app)
    response = client.get(f"/trace/{trace_id}")

    with open('traced_log.json', 'w') as f:
        json.dump(response.json(), f, indent=4, sort_keys=True)

if __name__ == "__main__":
    try:
        get_trace("18ed229c2f62599759d2e78834316ec2")
        # research_solve_problem()
        print("Test passed!")
    except AssertionError as e:
        print(f"Test failed as expected (or unexpected): {e}")
    except Exception as e:
        print(f"An error occurred: {e}")
