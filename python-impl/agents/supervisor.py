"""
Supervisor 编排 Agent，负责校园客服多 Agent 的路由与结果汇总。
"""

from __future__ import annotations

from typing import Annotated, Any, Optional, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from agents.compliance_checker import ComplianceCheckerAgent
from agents.general_chat import GeneralChatAgent
from agents.intent_router import IntentRouterAgent
from agents.knowledge_rag import KnowledgeRAGAgent
from agents.ticket_handler import TicketHandlerAgent
from memory.long_term import LongTermMemory
from memory.short_term import ShortTermMemory
from memory.working_memory import WorkingMemory
from tracing.otel_config import trace_agent_call
from llm_client import OpenAICompatibleChatModel, create_chat_model
from trace_utils import add_trace


class AgentState(TypedDict):
    """Supervisor 编排的全局状态。"""

    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    session_id: str
    intent: str
    sub_results: dict[str, Any]
    compliance_passed: bool
    final_response: str
    current_agent: str
    retry_count: int
    trace: list[dict[str, str]]


SUPERVISOR_SYSTEM_PROMPT = """你是校园智能客服系统的 Supervisor。

你的职责是：
1. 分析用户诉求并选择最合适的子 Agent
2. 汇总子 Agent 的结果，生成最终回复
3. 确保所有输出都经过内容安全与隐私审查

可用的子 Agent：
- knowledge_rag：回答选课、考试、报到、校园卡、奖助学金、宿舍与校园生活问题
- ticket_handler：处理宿舍报修、校园卡挂失、投诉建议、人工转办等服务工单
- compliance_checker：审查回复中的隐私、安全和越权承诺问题

请根据用户最新消息，返回下一步要路由到的 Agent 名称。
只返回以下三个值之一：knowledge_rag, ticket_handler, compliance_checker
"""


class SupervisorNode:
    """Supervisor 决策节点。"""

    def __init__(self, llm: OpenAICompatibleChatModel, working_memory: WorkingMemory):
        self.llm = llm
        self.working_memory = working_memory

    @trace_agent_call("supervisor")
    async def route_decision(self, state: AgentState) -> AgentState:
        """根据上下文决定路由。"""
        messages = state["messages"]
        session_id = state.get("session_id", "default")
        context = self.working_memory.get_context(session_id)
        user_message = str(messages[-1].content).strip().lower()
        trace = add_trace(state, "supervisor", "thinking", "Analyzing the request and selecting an agent")

        casual_inputs = (
            "\u4f60\u662f\u8c01", "\u4f60\u662f\u4ec0\u4e48", "\u4ecb\u7ecd\u4e00\u4e0b\u4f60\u81ea\u5df1",
            "\u4f60\u597d", "\u55e8", "hello", "hi", "\u4f60\u80fd\u505a\u4ec0\u4e48", "\u4f60\u4f1a\u4ec0\u4e48",
        )
        if any(item in user_message for item in casual_inputs):
            intent = "general_chat"
            self.working_memory.update(session_id, {"last_intent": intent})
            trace = add_trace({**state, "trace": trace}, "supervisor", "switch", "Switched to general_chat")
            return {**state, "intent": intent, "current_agent": "supervisor", "trace": trace}

        # Use deterministic routing for the supported campus workflows. Everything
        # else remains an open-ended conversation instead of failing RAG lookup.
        ticket_terms = (
            "\u62a5\u4fee", "\u6302\u5931", "\u8865\u529e", "\u5de5\u5355", "\u6295\u8bc9",
            "\u4eba\u5de5", "\u6f0f\u6c34", "\u5bbf\u820d\u6545\u969c", "\u6821\u56ed\u5361\u4e22\u5931",
        )
        knowledge_terms = (
            "\u9009\u8bfe", "\u8bfe\u7a0b", "\u8003\u8bd5", "\u6210\u7ee9", "\u5b66\u7c4d",
            "\u5956\u5b66\u91d1", "\u52a9\u5b66\u91d1", "\u6821\u56ed\u5361", "\u56fe\u4e66\u9986", "\u62a5\u5230",
        )
        if any(term in user_message for term in ticket_terms):
            intent = "ticket_handler"
        elif any(term in user_message for term in knowledge_terms):
            intent = "knowledge_rag"
        else:
            intent = "general_chat"
        self.working_memory.update(session_id, {"last_intent": intent})
        trace = add_trace({**state, "trace": trace}, "supervisor", "switch", f"Switched to {intent}")
        return {**state, "intent": intent, "current_agent": "supervisor", "trace": trace}

        routing_prompt = [
            SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT),
            SystemMessage(content=f"当前工作记忆上下文: {context}"),
            *messages,
            HumanMessage(
                content=(
                    "请只返回应该路由到的 Agent 名称，不要解释原因。"
                )
            ),
        ]

        response = await self.llm.ainvoke(routing_prompt)
        intent = response.content.strip().lower()

        valid_intents = {"knowledge_rag", "ticket_handler", "compliance_checker", "general_chat"}
        if intent not in valid_intents:
            intent = "general_chat"

        self.working_memory.update(session_id, {"last_intent": intent})

        return {
            **state,
            "intent": intent,
            "current_agent": "supervisor",
        }

    @trace_agent_call("supervisor_synthesize")
    async def synthesize_response(self, state: AgentState) -> AgentState:
        """汇总子 Agent 结果并生成最终回复。"""
        sub_results = state.get("sub_results", {})
        compliance_passed = state.get("compliance_passed", True)
        trace = add_trace(state, "supervisor", "thinking", "Combining agent results into the final response")

        if not compliance_passed:
            final_response = (
                "抱歉，这条请求涉及隐私、安全或超出权限范围的内容，"
                "我已建议转交校园人工服务老师进一步处理。"
            )
        else:
            result_parts = [
                result
                for result in sub_results.values()
                if isinstance(result, str) and result.strip()
            ]
            final_response = (
                "\n\n".join(result_parts)
                if result_parts
                else "抱歉，当前暂时无法完成这项校园服务请求，请稍后再试。"
            )

        return {
            **state,
            "final_response": final_response,
            "messages": [AIMessage(content=final_response)],
            "trace": add_trace({**state, "trace": trace}, "supervisor", "complete", "Response ready"),
        }


def route_to_agent(state: AgentState) -> str:
    """根据意图路由到对应节点。"""
    intent = state.get("intent", "knowledge_rag")
    route_map = {
        "knowledge_rag": "knowledge_rag",
        "ticket_handler": "ticket_handler",
        "compliance_checker": "compliance_check",
        "general_chat": "general_chat",
    }
    return route_map.get(intent, "knowledge_rag")


def create_supervisor_graph(
    llm: Optional[OpenAICompatibleChatModel] = None,
    working_memory: Optional[WorkingMemory] = None,
    short_term_memory: Optional[ShortTermMemory] = None,
    long_term_memory: Optional[LongTermMemory] = None,
    enable_checkpointing: bool = True,
) -> StateGraph:
    """构建校园客服多 Agent StateGraph。"""
    import os

    if llm is None:
        llm = create_chat_model()
    if working_memory is None:
        working_memory = WorkingMemory()

    supervisor = SupervisorNode(llm, working_memory)

    intent_router = IntentRouterAgent(llm)
    knowledge_agent = KnowledgeRAGAgent(llm, long_term_memory)
    ticket_agent = TicketHandlerAgent(llm)
    compliance_agent = ComplianceCheckerAgent(llm)
    general_chat_agent = GeneralChatAgent(llm)

    graph = StateGraph(AgentState)

    graph.add_node("supervisor_route", supervisor.route_decision)
    graph.add_node("knowledge_rag", knowledge_agent.process)
    graph.add_node("ticket_handler", ticket_agent.process)
    graph.add_node("compliance_check", compliance_agent.process)
    graph.add_node("general_chat", general_chat_agent.process)
    graph.add_node("synthesize", supervisor.synthesize_response)

    graph.set_entry_point("supervisor_route")
    graph.add_conditional_edges(
        "supervisor_route",
        route_to_agent,
        {
            "knowledge_rag": "knowledge_rag",
            "ticket_handler": "ticket_handler",
            "compliance_check": "compliance_check",
            "general_chat": "general_chat",
        },
    )

    graph.add_edge("knowledge_rag", "compliance_check")
    graph.add_edge("ticket_handler", "compliance_check")
    graph.add_edge("general_chat", "compliance_check")
    graph.add_edge("compliance_check", "synthesize")
    graph.add_edge("synthesize", END)

    checkpointer = MemorySaver() if enable_checkpointing else None
    return graph.compile(checkpointer=checkpointer)
