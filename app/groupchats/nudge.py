import asyncio
from typing import Sequence, List, Callable, Any, Mapping
from typing_extensions import Self

from autogen_agentchat.teams._group_chat._base_group_chat_manager import BaseGroupChatManager
from autogen_agentchat.teams._group_chat._base_group_chat import BaseGroupChat
from autogen_agentchat.teams._group_chat._events import GroupChatTermination
from autogen_agentchat.messages import BaseAgentEvent, BaseChatMessage, TextMessage, ToolCallRequestEvent, ToolCallExecutionEvent
from autogen_agentchat.base import ChatAgent, Team, TerminationCondition
from autogen_core import AgentRuntime, Component

# Reuse the config model or define a new one if you need extra fields
from autogen_agentchat.teams._group_chat._round_robin_group_chat import RoundRobinGroupChatConfig

class ConditionalNudgeManager(BaseGroupChatManager):
    """
    A manager that enforces a single-agent loop but interrupts with a 
    'nudge' agent upon detecting specific deterministic patterns (stagnation).
    """

    def __init__(
        self,
        name: str,
        group_topic_type: str,
        output_topic_type: str,
        participant_topic_types: List[str],
        participant_names: List[str],
        participant_descriptions: List[str],
        output_message_queue: asyncio.Queue[BaseAgentEvent | BaseChatMessage | GroupChatTermination],
        termination_condition: TerminationCondition | None,
        max_turns: int | None,
        message_factory: Any,
        emit_team_events: bool,
    ) -> None:
        super().__init__(
            name,
            group_topic_type,
            output_topic_type,
            participant_topic_types,
            participant_names,
            participant_descriptions,
            output_message_queue,
            termination_condition,
            max_turns,
            message_factory,
            emit_team_events,
        )
        # We assume the last agent in the list is the Nudge Agent, 
        # and the first is the Main Agent.
        # You could also look them up by name if you passed that in config.
        self._main_agent_name = participant_names[0]
        self._nudge_agent_name = participant_names[-1] 

    async def select_speaker(self, thread: Sequence[BaseAgentEvent | BaseChatMessage]) -> str:
        """
        Determines the next speaker based on the nudge condition.
        """
        # 1. Filter relevant messages to check the condition
        # We look at the message history to find the last two distinct interactions
        # We are only interested in TextMessage, ToolCallRequest, or ToolCallExecution
        # to determine 'stagnation'.
        
        if len(thread) < 2:
            return self._main_agent_name

        # Get the last two messages
        last_msg = thread[-1]
        penultimate_msg = thread[-2]

        # Check Condition: 2 text messages in a row uninterrupted
        # We must ensure they are TextMessages and NOT Tool Calls
        is_last_text = isinstance(last_msg, TextMessage)
        is_penultimate_text = isinstance(penultimate_msg, TextMessage)
        
        # We also need to ensure the last speaker was the Main Agent.
        # If the Nudge agent just spoke, we MUST return control to Main Agent.
        if last_msg.source == self._nudge_agent_name:
             return self._main_agent_name

        # THE LOGIC:
        # If both are text messages from the main agent, trigger the nudge.
        if (is_last_text and is_penultimate_text and 
            last_msg.source == self._main_agent_name and 
            penultimate_msg.source == self._main_agent_name):
            
            # Detected stagnation/looping without tools. Activate Nudge.
            return self._nudge_agent_name

        # Default behavior: Keep the Main Agent in the loop.
        return self._main_agent_name

    async def validate_group_state(self, messages: List[BaseChatMessage] | None) -> None:
        pass

    async def reset(self) -> None:
        self._current_turn = 0
        self._message_thread.clear()
        if self._termination_condition is not None:
            await self._termination_condition.reset()

    async def save_state(self) -> Mapping[str, Any]:
        return {
            "message_thread": [message.dump() for message in self._message_thread],
            "current_turn": self._current_turn,
        }

    async def load_state(self, state: Mapping[str, Any]) -> None:
        self._message_thread = [self._message_factory.create(message) for message in state["message_thread"]]
        self._current_turn = state["current_turn"]


class NudgeGroupChat(BaseGroupChat, Component[RoundRobinGroupChatConfig]):
    """
    A custom Team implementation that utilizes the ConditionalNudgeManager.
    Expected participants: [MainAgent, NudgeAgent]
    """
    
    component_config_schema = RoundRobinGroupChatConfig
    component_provider_override = "autogen_agentchat.teams.NudgeGroupChat"

    DEFAULT_NAME = "NudgeGroupChat"
    DEFAULT_DESCRIPTION = "A team where a nudge agent interrupts a main agent if it stagnates."

    def __init__(
        self,
        participants: List[ChatAgent | Team],
        *,
        name: str | None = None,
        description: str | None = None,
        termination_condition: TerminationCondition | None = None,
        max_turns: int | None = None,
        runtime: AgentRuntime | None = None,
        custom_message_types: List[type[BaseAgentEvent | BaseChatMessage]] | None = None,
        emit_team_events: bool = False,
    ) -> None:
        super().__init__(
            name=name or self.DEFAULT_NAME,
            description=description or self.DEFAULT_DESCRIPTION,
            participants=participants,
            group_chat_manager_name="ConditionalNudgeManager",
            group_chat_manager_class=ConditionalNudgeManager, # Inject our custom manager
            termination_condition=termination_condition,
            max_turns=max_turns,
            runtime=runtime,
            custom_message_types=custom_message_types,
            emit_team_events=emit_team_events,
        )

    # We must implement the factory creator to pass arguments to our custom Manager
    def _create_group_chat_manager_factory(
        self,
        name: str,
        group_topic_type: str,
        output_topic_type: str,
        participant_topic_types: List[str],
        participant_names: List[str],
        participant_descriptions: List[str],
        output_message_queue: asyncio.Queue[BaseAgentEvent | BaseChatMessage | GroupChatTermination],
        termination_condition: TerminationCondition | None,
        max_turns: int | None,
        message_factory: Any,
    ) -> Callable[[], ConditionalNudgeManager]:
        def _factory() -> ConditionalNudgeManager:
            return ConditionalNudgeManager(
                name,
                group_topic_type,
                output_topic_type,
                participant_topic_types,
                participant_names,
                participant_descriptions,
                output_message_queue,
                termination_condition,
                max_turns,
                message_factory,
                self._emit_team_events,
            )
        return _factory

    # Implementation of serialization methods (_to_config, _from_config) 
    # would mirror the RoundRobin implementation provided in your prompt.
    def _to_config(self) -> RoundRobinGroupChatConfig:
        participants = [participant.dump_component() for participant in self._participants]
        termination_condition = self._termination_condition.dump_component() if self._termination_condition else None
        return RoundRobinGroupChatConfig(
            name=self._name,
            description=self._description,
            participants=participants,
            termination_condition=termination_condition,
            max_turns=self._max_turns,
            emit_team_events=self._emit_team_events,
        )

    @classmethod
    def _from_config(cls, config: RoundRobinGroupChatConfig) -> Self:
        participants: List[ChatAgent | Team] = []
        for participant in config.participants:
            if participant.component_type == Team.component_type:
                participants.append(Team.load_component(participant))
            else:
                participants.append(ChatAgent.load_component(participant))

        termination_condition = (
            TerminationCondition.load_component(config.termination_condition) if config.termination_condition else None
        )
        return cls(
            participants,
            name=config.name,
            description=config.description,
            termination_condition=termination_condition,
            max_turns=config.max_turns,
            emit_team_events=config.emit_team_events,
        )