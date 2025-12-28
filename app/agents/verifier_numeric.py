from autogen_agentchat.ui import Console
import sympy as sp
from app.tracing import traced
import mpmath as mp
import traceback
from app.config import POLYMATH_SERVER_URL, model_client
from app.work import AgentWork
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import FunctionCallTermination
from concurrent.futures import ProcessPoolExecutor
import asyncio


TIME_LIMIT_SECONDS = 60
executor = None  # defined globally

def setup_executor():
    global executor
    executor = ProcessPoolExecutor()

async def verify_solution(proposed_solution_code: str) -> str:
    loop = asyncio.get_running_loop()
    
    try:
        result = await asyncio.wait_for(
                loop.run_in_executor(executor, _verification_worker, proposed_solution_code),
                timeout=TIME_LIMIT_SECONDS
        )
        return result
        
    except asyncio.TimeoutError:
        return "VERDICT:INCONCLUSIVE\nMESSAGE:Timeout"

def _verification_worker(code: str) -> str:

    """Run the user-provided verification code in an isolated process."""
    env = {
        "sympy": sp,
        "sp": sp,
        "mpmath": mp,
        "mp": mp,
    }

    try:
        exec(code, env, env)
        if "verification_passed" in env:
            passed = bool(env["verification_passed"])
            msg = env.get("verification_message", "")
            if passed:
                return(f"Verification successful. {msg}")
            else:  
                return(f"Verification failed. {msg}")
        else:
            verification_result = env.get(
                "verification_output",
                "Code executed, but no explicit verification flag was provided.",
            )
            return(
                f"Verification successful (no explicit flag). "
                f"Result: {verification_result}"
            )

    except AssertionError as e:
        return(f"Verification failed. AssertionError: {e}")
    except Exception as e:
        tb = traceback.format_exc()
        return (
            f"Verification failed. Error during execution: {e}\nTraceback:\n{tb}"
        )

verifier_sys = """
# Identity 
You are a numeric/symbolic verification agent. 
Your job is to verify, using the tools provided to you -- Python interpreter with SymPy and mpmath -- mathematical claims and implications.
Do NOT submit your own prose, instead just rely on the results of the tools.

# Tips for verification
- When writing code for the interpreter to verify, set a boolean flag `verification_passed` to signal whether the verification failed or succeeded.
- You can also set a string variable `verification_message` to indicate the detailed cause of failure or pass.
- Any Python errors will make the verification automatically fail.

# Verification success
- A verification can only be successful IF and ONLY IF you have successfully verified it by running code, with code remaining faithful to the 
initial problem.

# Your verdict
- When either the verification with SymPy or numeric methods was successful, you can use `submit_verification_results` tool to give a final reason, and state the reason why you gave the answer as such.
- When the verification fails, if it's due to a Python error unrelated to the statement/implication at hand, retry the verification.
- When you determine the statement cannot be verified with the tools either due to a logical error (implied by tools), or due to limitations of the tools, also use the `submit_verification_results` tool to finalize the conversation.
"""

class NumericVerifierWork(AgentWork):
    def submit_verification_results(self, verified_sympy_or_numeric: bool, tool_verification_success_or_failure_reason: str):
        """Submit your SymPy/numeric verification results, with a reason for the result."""
        self.result = f"VERIFICATION SUCCESS: {verified_sympy_or_numeric} \n\n STATED REASON: {tool_verification_success_or_failure_reason}"



@traced
async def verify_numeric(task: str):
    """Allocates a sub-agent to run numeric/symbolic verification with SymPy and other Python libraries."""

    state = NumericVerifierWork()
    numeric_verifier_agent = AssistantAgent(
        name="numeric_verifier",
        model_client=model_client,
        tools=[state.submit_verification_results, verify_solution],
        system_message=verifier_sys
    )

    team = RoundRobinGroupChat(
        [numeric_verifier_agent],
        termination_condition=FunctionCallTermination("submit_verification_results")
    )

    await Console(team.run_stream(task=task))

    return state.result

    