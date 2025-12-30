from autogen_agentchat.agents._base_chat_agent import BaseChatAgent
from autogen_agentchat.messages import BaseChatMessage, TextMessage
from autogen_agentchat.base import Response
from typing import Sequence, Any

class DeterministicNudgeAgent(BaseChatAgent):
    """
    An agent that returns a fixed template message whenever it is invoked.
    It performs no inference and requires no model client.
    """
    
    def __init__(self, name: str, message_content: str, description: str = "A nudge agent."):
        super().__init__(name=name, description=description)
        self._message_content = message_content

    @property
    def produced_message_types(self) -> Sequence[type[BaseChatMessage]]:
        return (TextMessage,)
        
    async def on_messages(
        self, 
        messages: Sequence[BaseChatMessage], 
        cancellation_token: Any = None
    ) -> Response:
        """
        Ignores input history and returns the static template message.
        """
        return Response(
            chat_message=TextMessage(
                content=self._message_content,
                source=self.name
            )
        )

    async def on_reset(self, cancellation_token: Any = None) -> None:
        pass