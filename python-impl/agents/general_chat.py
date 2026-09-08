"""General conversation agent for questions outside the campus knowledge base."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from llm_client import OpenAICompatibleChatModel
from tracing.otel_config import trace_agent_call
from trace_utils import add_trace


GENERAL_CHAT_PROMPT = """You are a helpful, concise campus customer-service assistant.
Answer normal conversation, greetings, identity questions, and general questions naturally.
Do not invent official campus policies or claim to perform actions you cannot perform.
Reply in the same language as the user."""


class GeneralChatAgent:
    """Handles open-ended dialogue without a knowledge-base match."""

    def __init__(self, llm: OpenAICompatibleChatModel):
        self.llm = llm

    @trace_agent_call("general_chat_process")
    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        messages = state.get("messages", [])
        if not messages:
            return state

        trace = add_trace(state, "general_chat", "thinking", "Generating a direct answer with the configured model")
        response = await self.llm.ainvoke(
            [
                SystemMessage(content=GENERAL_CHAT_PROMPT),
                HumanMessage(content=str(messages[-1].content)),
            ]
        )
        return {
            **state,
            "sub_results": {
                **state.get("sub_results", {}),
                "general_chat": str(response.content),
            },
            "trace": add_trace({**state, "trace": trace}, "general_chat", "complete", "General answer generated"),
        }
