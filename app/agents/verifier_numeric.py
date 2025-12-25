import sympy as sp
import mpmath as mp
import multiprocessing as mp_proc
import traceback
from app.config import POLYMATH_SERVER_URL, model_client
from app.work import AgentWork
import subprocess
from pydantic import BaseModel
from polymath_schemas.api_requests import NodePatchRequest
from polymath_schemas.graph import VerificationLevel
import requests
from autogen_agentchat.agents import AssistantAgent
from functools import partial
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import FunctionCallTermination



TIME_LIMIT_SECONDS = 10


def _verification_worker(code: str, out_queue: "mp_proc.Queue") -> None:
    """Run the user-provided verification code in an isolated process."""
    env = {
        "sympy": sp,
        "sp": sp,
        "mpmath": mp,
        "mp": mp,
    }
    try:
        # Use the same dict for globals and locals
        exec(code, env, env)

        if "verification_passed" in env:
            passed = bool(env["verification_passed"])
            msg = env.get("verification_message", "")
            if passed:
                out_queue.put(f"Verification successful. {msg}")
            else:
                out_queue.put(f"Verification failed. {msg}")
        else:
            verification_result = env.get(
                "verification_output",
                "Code executed, but no explicit verification flag was provided.",
            )
            out_queue.put(
                f"Verification successful (no explicit flag). "
                f"Result: {verification_result}"
            )
    except AssertionError as e:
        out_queue.put(f"Verification failed. AssertionError: {e}")
    except Exception as e:
        tb = traceback.format_exc()
        out_queue.put(
            f"Verification failed. Error during execution: {e}\nTraceback:\n{tb}"
        )

def verify_solution(proposed_solution_code: str) -> str:
    """
    Execute proposed verification code in an isolated process with a time limit.

    The user code must set either:
      - verification_passed = True/False and optionally verification_message, OR
      - verification_output for a generic result.

    This function returns a structured, parseable string:

        VERDICT:PASS
        MESSAGE:<human-readable message>

        VERDICT:FAIL
        MESSAGE:<human-readable message>

        VERDICT:INCONCLUSIVE
        MESSAGE:<human-readable message>

    Any exception or timeout is treated as INCONCLUSIVE (tooling / environment issue),
    not as a mathematical FAIL.
    """
    q: mp_proc.Queue = mp_proc.Queue()
    p = mp_proc.Process(
        target=_verification_worker,
        args=(proposed_solution_code, q),
    )

    p.start()
    p.join(TIME_LIMIT_SECONDS)

    if p.is_alive():
        # Time limit exceeded
        p.terminate()
        p.join()
        return (
            "VERDICT:INCONCLUSIVE\n"
            f"MESSAGE:Verification failed. Error during execution: timeout after {TIME_LIMIT_SECONDS} seconds."
        )

    try:
        raw = q.get_nowait()
    except Exception:
        return (
            "VERDICT:INCONCLUSIVE\n"
            "MESSAGE:Verification failed. No result returned from verification process."
        )

    msg = raw.strip()

    # Map worker messages to structured verdicts
    if msg.startswith("Verification successful."):
        return f"VERDICT:PASS\nMESSAGE:{msg}"

    if msg.startswith("Verification successful (no explicit flag)."):
        return f"VERDICT:PASS\nMESSAGE:{msg}"

    if msg.startswith("Verification failed. AssertionError"):
        # Explicit assertion means the mathematical check failed
        return f"VERDICT:FAIL\nMESSAGE:{msg}"

    if msg.startswith("Verification failed. Error during execution"):
        # SymPy / numeric / environment issues → inconclusive
        return f"VERDICT:INCONCLUSIVE\nMESSAGE:{msg}"

    if msg.startswith("Verification failed."):
        # Covers verification_passed = False with custom message
        return f"VERDICT:FAIL\nMESSAGE:{msg}"

    # Fallback if message is unexpected
    return f"VERDICT:INCONCLUSIVE\nMESSAGE:{msg}"

class VerifierVerdict(BaseModel):
    verified: bool
    reason: str

def give_verdict(verdict: VerifierVerdict, node_id: str, verification_level: int):
    """
    Use this tool when you've reached a conclusion about the verifiability of the statement with your given tools.
    """
    # patch and then also comment with the reason
    if verdict.verified:
        req_body = NodePatchRequest(
            verification=verification_level
        )
        requests.patch(
            POLYMATH_SERVER_URL + f"/graph/nodes/{node_id}",
            json=req_body.model_dump()
        )
    

    requests.post(
        POLYMATH_SERVER_URL + f"/graph/nodes/{node_id}/comment",
        json=verdict.reason
    )


verifier_sys = """
# Identity 
You are a numeric/symbolic verification agent. 
Your job is to verify, using the tools provided to you -- Python interpreter with SymPy and mpmath -- mathematical claims and implications.

# Tips for verification
- When writing code for the interpreter to verify, set a boolean flag `verification_passed` to signal whether the verification failed or succeeded.
- You can also set a string variable `verification_message` to indicate the detailed cause of failure or pass.
- Any Python errors will make the verification automatically fail.

# Your verdict
- When either the verification was successful, you can use `give_verdict` tool to give a final reason, and state the reason why you gave the answer as such.
- When the verification fails, if it's due to a Python error unrelated to the statement/implication at hand, retry the verification.
- When you determine the statement cannot be verified either due to a logical error, or due to limitations of the tools, also use the `give_verdict` tool to finalize the conversation.
"""




async def verify_numeric(task: str):
    """Allocates a sub-agent to run numeric/symbolic verification with SymPy and other Python libraries."""

    state = AgentWork()
    numeric_verifier_agent = AssistantAgent(
        name="numeric_verifier",
        model_client=model_client,
        tools=[state.submit_answer, verify_solution],
        system_message=verifier_sys
    )

    team = RoundRobinGroupChat(
        [numeric_verifier_agent],
        termination_condition=FunctionCallTermination("give_verdict")
    )

    await team.run(task=task)

    return state.result

    