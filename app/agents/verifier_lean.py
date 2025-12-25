# autogen
from app.config import model_client
from app.work import AgentWork
from autogen_agentchat.agents import AssistantAgent
from app.agents.verifier_numeric import give_verdict
from polymath_schemas.graph import VerificationLevel
from autogen_agentchat.conditions import FunctionCallTermination
from autogen_agentchat.teams import RoundRobinGroupChat
import json
import subprocess
from typing import Optional, List, Dict, Any
from functools import partial
import asyncio
import json
import os
from typing import Optional

class AsyncLean4REPL:
    def __init__(self, project_path: str = "."):
        self.project_path = project_path
        self.process: Optional[asyncio.subprocess.Process] = None
        self.env: Optional[int] = None
        # A lock is crucial! It prevents the agent from sending a second command 
        # before the first one finishes, which would corrupt the REPL state.
        self._lock = asyncio.Lock()

    async def _ensure_process(self):
        """Lazily starts the Lean REPL process."""
        if self.process is None:
            self.process = await asyncio.create_subprocess_exec(
                "lake", "exe", "repl",
                cwd=self.project_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

    async def run_command(self, lean_code: str) -> str:
        """Async function to send commands to Lean."""
        async with self._lock:
            await self._ensure_process()
            
            if not lean_code.strip():
                return "Empty command."

            # Construct request
            request : dict[str, Any] = {"cmd": lean_code}
            if self.env is not None:
                request["env"] = self.env

            try:
                assert self.process is not None
                assert self.process.stdin is not None
                assert self.process.stdout is not None
                
                # WRITE (Non-blocking)
                json_req = json.dumps(request) + "\n"
                self.process.stdin.write(json_req.encode("utf-8"))
                await self.process.stdin.drain()

                # READ (Non-blocking)
                # This await releases the event loop while Lean computes
                response_bytes = await self.process.stdout.readline()
                
                if not response_bytes:
                    return "Error: Lean REPL process died."
                
                response = json.loads(response_bytes.decode("utf-8"))
            
            except Exception as e:
                return f"System Error: {str(e)}"

            # Update State
            if "env" in response:
                self.env = response["env"]

            return self._format_output(response)

    def _format_output(self, response: dict) -> str:
        """Helper to format JSON into a string for the LLM."""
        output = []
        if "messages" in response:
            for msg in response["messages"]:
                output.append(f"[{msg.get('severity', 'info')}]: {msg.get('data', '')}")
        if "sorries" in response:
            for sorry in response["sorries"]:
                output.append(f"--- Goal ---\n{sorry.get('goal', '')}")
        if not output:
             output.append("Command accepted.")
        return "\n".join(output)

    async def close(self):
        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except ProcessLookupError:
                pass
        
repl_tool = AsyncLean4REPL()

async def lean_tool(command: str) -> str:
    """
    Execute a Lean 4 command or tactic. 
    Returns the new goal state or errors.
    Use this to prove theorems step-by-step.
    """
    return await repl_tool.run_command(command)

lean_verifier_sys = """You are a formal verification expert in Lean 4. 
You have access to a persistent Lean REPL.
1. Declare theorems using 'theorem name ...'
2. Prove them step-by-step.
3. If you get an error, read it and correct your tactic.
4. When the goal is empty, the proof is complete.

Then, when your proving process concludes (either success or failure), call the 
`give_verdict` tool to report your findings, with a stated reason to the outcome.
"""

async def verify_lean(lean_task: str):
    """Allocates a sub-agent to attempt to verify things formally with Lean theorem prover."""
    state = AgentWork()
    agent = AssistantAgent(
        name="lean_verifier",
        system_message=lean_verifier_sys,
        model_client=model_client,
        tools=[lean_tool, state.submit_answer],
    )

    team = RoundRobinGroupChat(
        [agent],
        termination_condition=FunctionCallTermination("give_verdict")
    )

    await team.run(task=lean_task)

    return state.result