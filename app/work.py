
from pydantic.fields import Field
from functools import partial
from typing import AsyncGenerator, Awaitable, Callable, Dict, List, Optional, TypeVar, Union, cast
from pydantic import BaseModel
from autogen_core import CancellationToken
from autogen_core.models import RequestUsage

from autogen_agentchat.agents import UserProxyAgent
from autogen_agentchat.base import Response, TaskResult
from autogen_agentchat.messages import (
    BaseAgentEvent,
    BaseChatMessage,
    ModelClientStreamingChunkEvent,
    MultiModalMessage,
    UserInputRequestedEvent,
)

class ChatLog(BaseModel):
    msgs: list[str] = Field(default_factory=list)
    subagents_logs: list = Field(default_factory=list) # those are also of the ChatLog type


class AgentWork(BaseModel):
    result: Optional[str] = None
    log: ChatLog = Field(default_factory=ChatLog) 

    def submit_answer(self, report: str) -> str:
        """Use this tool to submit your final answer."""
        self.result = report
        return "Submitted."

    def get_history(self):
        return "\n".join([str(msg) for msg in self.log.msgs])


    async def log_stream(
        self,
        stream: AsyncGenerator[BaseAgentEvent | BaseChatMessage | TaskResult, None],
        # add parameter here for subagents, then submit work to the functions
    ):
        """
        Consumes the message stream from :meth:`~autogen_agentchat.base.TaskRunner.run_stream`
        or :meth:`~autogen_agentchat.base.ChatAgent.on_messages_stream` and saves it to a log 
        that will later be returned via an endpoint.
    """
        async for message in stream:
            print(message)
            self.log.msgs.append(message.model_dump_json())

    def get_subagent_func(self, func, work_type: type["AgentWork"]):
        work = work_type()
        self.log.subagents_logs.append(work.log)
        return partial(func, work=work, context=self.get_history()) # type: ignore

        