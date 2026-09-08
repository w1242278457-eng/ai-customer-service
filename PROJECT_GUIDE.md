# 校园智能客服多 Agent 项目完整说明

> 本文档面向需要运行、阅读、维护和继续扩展本项目的开发者。内容以当前仓库中的实际代码为准，重点解释前端、后端、模型接入、Agent 协作、记忆、RAG、工具、轨迹展示和部署方式。

## 1. 项目定位

这是一个面向校园服务场景的全栈智能客服系统。用户在网页中输入自然语言问题，后端由 FastAPI 提供接口，再由 LangGraph 编排多个专用 Agent，最后调用 DeepSeek 或其他 OpenAI-compatible 模型生成回答。

当前系统覆盖四类核心工作：

1. 普通对话：问候、身份介绍、开放式问题和不属于校园知识库的问题。
2. 校园知识问答：选课、考试、学籍、奖助学金、校园卡、报到等 FAQ。
3. 校园服务工单：宿舍报修、校园卡挂失/补办、投诉、人工转办等。
4. 回复安全检查：隐私信息、越权承诺、危险或违规表达检查。

项目的核心特点是“一个入口、多个专用 Agent、统一编排和统一安全检查”。用户不需要知道后端有多少个 Agent，只需要提交问题；Supervisor 会决定应该交给哪个 Agent，子 Agent 完成任务后再交给合规 Agent 检查，最后由 Supervisor 汇总成一条回复。

## 2. 当前实现边界

下面这些能力已经在代码中实现：

- FastAPI 后端和内置 Web 前端。
- DeepSeek Chat Completions API 接入。
- 其他 OpenAI-compatible 服务的配置兼容。
- 无 API Key 或模型请求失败时的本地 fallback 演示模式。
- LangGraph 状态图编排。
- 通用对话、知识库 RAG、工单、合规四类 Agent。
- Redis 短期记忆不可用时的进程内回退。
- FAISS 接口和关键词检索回退。
- MCP 风格工具注册、列表、调用和调用日志。
- OpenTelemetry Agent Span（安装依赖并启用时）和基础指标接口。
- 前端可选的执行轨迹弹窗，以及逐条追加的展示效果。

下面这些仍属于演示实现或需要继续完善：

- 工单数据当前保存在进程内存中，服务重启后会丢失。
- 长期记忆默认使用基于文本哈希的随机演示向量，不是真正的语义 Embedding。
- 预置知识库只有少量校园 FAQ 示例，不等同于学校正式政策库。
- `/api/chat` 当前是一次请求一次响应，不是后端 SSE/WebSocket 流式输出；前端收到完整响应后再播放轨迹。
- MCP 工具目前是本地模拟工具，不会自动连接真实教务、校园卡或后勤系统。
- 生产环境还需要认证、权限、限流、审计、密钥管理和持久化数据库。

## 3. 目录结构

```text
ai-customer-service/
├─ frontend/
│  └─ index.html                  # 原生 HTML/CSS/JavaScript 前端
├─ python-impl/
│  ├─ api/
│  │  └─ main.py                  # FastAPI 入口、生命周期和 REST API
│  ├─ agents/
│  │  ├─ supervisor.py             # Supervisor 和 LangGraph 状态图
│  │  ├─ general_chat.py           # 通用对话 Agent
│  │  ├─ knowledge_rag.py          # 知识库检索问答 Agent
│  │  ├─ ticket_handler.py         # 工单 Agent 和内存工单存储
│  │  ├─ compliance_checker.py     # 合规与隐私检查 Agent
│  │  └─ intent_router.py          # 可复用的 LLM 意图分类 Agent
│  ├─ memory/
│  │  ├─ working_memory.py         # 当前会话工作记忆
│  │  ├─ short_term.py             # Redis 短期对话记忆
│  │  └─ long_term.py              # FAISS/关键词长期知识记忆
│  ├─ mcp/
│  │  └─ mcp_server.py             # MCP 风格工具服务器和默认工具
│  ├─ tracing/
│  │  └─ otel_config.py             # OpenTelemetry 装饰器和指标
│  ├─ llm_client.py                # DeepSeek/OpenAI-compatible HTTP 客户端
│  ├─ trace_utils.py               # 安全的用户可见执行摘要
│  ├─ requirements.txt             # Python 依赖
│  ├─ Dockerfile                   # Python 服务镜像
│  ├─ .env.example                 # 配置模板
│  └─ .env                         # 本地真实配置，不应提交
├─ docker-compose.yml              # Redis、Agent 服务、Jaeger 编排
├─ README.md                       # 简短项目介绍
├─ PROJECT_GUIDE.md                # 本完整说明文档
└─ LICENSE
```

## 4. 技术栈与请求链路

### 4.1 技术栈

| 层次 | 技术 | 用途 |
|---|---|---|
| 前端 | 原生 HTML/CSS/JavaScript | 聊天界面、会话 ID、轨迹弹窗 |
| Web 服务 | FastAPI + Uvicorn | REST API、静态页面、Swagger 文档 |
| Agent 编排 | LangGraph | 状态、节点、条件路由和执行顺序 |
| 模型 | DeepSeek Chat Completions | 普通回答、RAG 改写/生成、工单抽取、合规判断 |
| 兼容层 | 自定义 `OpenAICompatibleChatModel` | 摆脱特定 OpenAI SDK 限制，统一 HTTP 协议 |
| 短期记忆 | Redis，失败时内存回退 | 保存最近多轮对话 |
| 长期记忆 | FAISS 接口，失败时关键词回退 | 保存和检索知识文档 |
| 工具 | MCP 风格注册/调用层 | 统一封装校园卡、检索、工单、安全工具 |
| 可观测性 | OpenTelemetry + Jaeger | Agent 调用 Span 和链路观察 |
| 部署 | Docker Compose | Redis、Python 服务和 Jaeger 一键启动 |

### 4.2 一次聊天请求的完整链路

```text
浏览器输入问题
  ↓ POST /api/chat
FastAPI 校验请求并生成/复用 session_id
  ↓
短期记忆保存 user 消息
  ↓
LangGraph graph.ainvoke(initial_state)
  ↓
Supervisor 分析问题并确定 intent
  ├─ general_chat
  ├─ knowledge_rag
  └─ ticket_handler
  ↓
对应子 Agent 处理任务
  ↓
compliance_checker 检查子 Agent 输出
  ↓
Supervisor synthesize 汇总最终回答
  ↓
短期记忆保存 assistant 消息
  ↓
返回 response、intent、compliance_passed、trace
  ↓
前端逐条播放安全的执行轨迹并显示最终回答
```

## 5. 启动和访问

### 5.1 本地 Python 启动

在 PowerShell 中执行：

```powershell
cd D:\简历\ai-customer-service\python-impl
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python -m api.main
```

然后访问：

```text
聊天页面： http://localhost:8000
Swagger：  http://localhost:8000/docs
健康检查： http://localhost:8000/health
```

如果 PowerShell 禁止激活虚拟环境，可以直接使用虚拟环境中的 Python：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m api.main
```

### 5.2 Docker Compose 启动

在项目根目录执行：

```powershell
docker compose up --build
```

Compose 会启动三个服务：

- `redis`：保存短期会话消息。
- `python-agent`：FastAPI 和 LangGraph 服务，映射到 `8000` 端口。
- `jaeger`：查看 OpenTelemetry Trace，界面通常是 `http://localhost:16686`。

Docker 读取项目根目录的环境变量或 `.env`。不要把真实 API Key 写进 Dockerfile 或提交到 Git。

## 6. 配置说明

配置文件模板是 `python-impl/.env.example`。最小 DeepSeek 配置如下：

```dotenv
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=填写你自己的密钥
LLM_BASE_URL=https://api.deepseek.com/v1
MODEL_NAME=deepseek-chat
LLM_TEMPERATURE=0
```

完整配置项说明：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `LLM_PROVIDER` | `deepseek` | 供应商名称，仅用于选择默认地址和前端状态展示 |
| `DEEPSEEK_API_KEY` | 空 | DeepSeek 密钥；为空时进入本地 fallback |
| `OPENAI_API_KEY` | 空 | 兼容其他 OpenAI-compatible 配置的备用环境变量 |
| `LLM_BASE_URL` | DeepSeek v1 地址 | Chat Completions 基础地址 |
| `MODEL_NAME` | `deepseek-chat` | 模型名称 |
| `LLM_TEMPERATURE` | `0` | 请求中的温度参数 |
| `REDIS_URL` | `redis://localhost:6379/0` | 短期记忆 Redis 地址 |
| `FAISS_INDEX_PATH` | `./vector_store/faiss_index` | FAISS 索引路径 |
| `OTEL_SERVICE_NAME` | `smart-cs-multi-agent` | Trace 服务名 |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | 空 | Jaeger/OTLP 地址；为空时使用控制台导出器 |
| `HOST` | `0.0.0.0` | Uvicorn 监听地址 |
| `PORT` | `8000` | Uvicorn 监听端口 |

### 6.1 模型客户端的工作方式

`python-impl/llm_client.py` 没有依赖固定的 OpenAI Python 客户端，而是通过 `httpx.AsyncClient` 发送标准 HTTP 请求：

```text
POST {LLM_BASE_URL}/chat/completions
Authorization: Bearer {API_KEY}
Content-Type: application/json
```

请求体包含 `model`、`messages` 和 `temperature`。LangChain 的 `HumanMessage`、`SystemMessage`、`AIMessage` 会被转换成标准的 `user`、`system`、`assistant` 角色。

因此，只要第三方服务兼容 Chat Completions 格式，就可以通过调整 `LLM_BASE_URL`、`MODEL_NAME` 和 Key 接入，不需要修改 Agent 代码。

### 6.2 无 Key 或请求失败时的 fallback

以下情况会使用本地演示回答：

- 没有配置 Key。
- Key 是模板中的占位值，例如 `local-` 或 `sk-your-` 开头。
- HTTP 请求失败或返回错误。

fallback 主要用于保证项目能启动、前端能演示、接口能联调。它不具备真实模型的开放式推理能力，也不应该被当作生产模型。

## 7. 前端详解

前端只有一个文件：`frontend/index.html`。FastAPI 启动时通过根路径 `/` 返回它，并把该目录挂载到 `/static`。

### 7.1 页面组成

- 顶部：项目名称和模型服务说明。
- 左侧：快捷问题按钮和模型配置状态。
- 中间：消息列表。
- 底部：文本输入框和发送按钮。
- 右上角：`显示思考轨迹` 开关。
- 轨迹面板：显示 Supervisor、RAG、工单、合规等状态节点。

页面没有 npm、Webpack 或 React 构建步骤，浏览器直接加载即可，适合当前项目快速部署和阅读。

### 7.2 会话管理

前端用 `sessionId` 保存当前会话 ID：

1. 第一次请求不携带 `session_id`。
2. 后端生成 UUID 并返回。
3. 前端保存返回的 ID。
4. 后续请求携带同一个 ID。

这样后端 Redis 或内存短期记忆可以把多次请求归到同一个会话中。

### 7.3 请求和响应

前端调用：

```javascript
fetch('/api/chat', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({message: text, session_id: sessionId})
})
```

收到响应后，先更新 `sessionId`，再播放 `trace`，最后把 `response` 添加到消息列表。

### 7.4 轨迹弹窗为什么是“逐渐增加”

前端定义了两套轨迹：

- 请求尚未返回时：先显示“读取问题”“选择 Agent”“准备模型请求”等等待节点。
- 请求返回后：使用后端真实返回的 `trace`，每约 380ms 添加一条。

这会形成“分析 → 切换 Agent → 执行 → 合规检查 → 汇总”的渐进式视觉效果。

需要特别理解：当前 `/api/chat` 是普通 HTTP 请求，后端不会在执行过程中把节点实时推送给浏览器。等待阶段的节点是前端占位动画，返回后的节点是后端执行完成后返回的安全摘要。若要真正实时显示，需要把接口改造成 SSE、WebSocket 或 LangGraph 流式事件接口。

### 7.5 思考轨迹与私有思维链的边界

`trace_utils.py` 只记录如下类型的摘要：

```json
{
  "agent": "knowledge_rag",
  "event": "thinking",
  "detail": "Searching the campus knowledge base"
}
```

前端显示的是 Agent 执行状态，不是模型逐字的私有 CoT。这样既能让用户理解任务进度，又不会泄露系统提示词、隐私数据、内部决策细节或模型隐藏推理。后续新增轨迹时也应保持“状态摘要”粒度。

## 8. FastAPI 后端详解

入口文件是 `python-impl/api/main.py`。

### 8.1 应用初始化

模块加载时创建全局组件：

- `WorkingMemory`
- `ShortTermMemory`
- `LongTermMemory`
- `MCPToolServer`
- `AgentMetrics`

应用生命周期 `lifespan()` 启动时会：

1. 初始化 OpenTelemetry。
2. 创建 LangGraph Supervisor 图。
3. 写入预置校园 FAQ 文档。
4. 开始接受请求。

### 8.2 API 清单

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/` | 返回聊天前端 |
| `GET` | `/health` | 健康检查 |
| `GET` | `/api/config` | 返回非敏感模型配置状态 |
| `POST` | `/api/chat` | 处理一轮聊天 |
| `GET` | `/api/history/{session_id}` | 查询短期会话历史 |
| `GET` | `/api/tools` | 列出已注册工具 |
| `POST` | `/api/tools/call` | 调用一个工具 |
| `GET` | `/api/metrics` | 返回指标和最近工具调用日志 |
| `GET` | `/docs` | FastAPI Swagger 文档 |

### 8.3 `POST /api/chat`

请求：

```json
{
  "message": "宿舍漏水，怎么报修？",
  "user_id": "anonymous",
  "session_id": "可选的已有会话 ID"
}
```

响应：

```json
{
  "response": "最终回复文本",
  "session_id": "会话 UUID",
  "intent": "ticket_handler",
  "compliance_passed": true,
  "trace": [
    {
      "agent": "supervisor",
      "event": "thinking",
      "detail": "Analyzing the request and selecting an agent"
    }
  ]
}
```

后端不把 API Key 返回给前端。`/api/config` 只返回 provider、model 和 `configured: true/false`。

### 8.4 `GET /api/history/{session_id}`

返回 Redis 或内存回退中的最近消息。默认短期记忆最多保留 20 条消息，并设置 1800 秒 TTL（Redis 模式）。

### 8.5 工具 API

`GET /api/tools` 返回工具名称、描述、输入 Schema 和分类。`POST /api/tools/call` 的请求格式：

```json
{
  "name": "service_ticket_create",
  "arguments": {
    "title": "宿舍漏水",
    "description": "请后勤处理",
    "priority": "high"
  }
}
```

注意：工具 API 当前是显式调用接口，主聊天流程中的 Ticket Agent 并不会自动调用所有 MCP 工具。

## 9. Agent 协作机制

### 9.1 LangGraph 状态

`agents/supervisor.py` 定义 `AgentState`，节点之间传递同一个状态对象。重要字段如下：

| 字段 | 作用 |
|---|---|
| `messages` | LangChain 消息列表 |
| `user_id` | 当前用户标识 |
| `session_id` | 会话隔离键 |
| `intent` | Supervisor 选择的业务意图 |
| `sub_results` | 子 Agent 结果 |
| `compliance_passed` | 合规是否通过 |
| `final_response` | 最终输出 |
| `current_agent` | 当前 Agent 名称 |
| `retry_count` | 重试计数预留字段 |
| `trace` | 用户可见的执行摘要列表 |

### 9.2 Supervisor 路由

当前主流程使用确定性关键词路由，优先保证支持的校园流程稳定：

- 工单关键词：报修、挂失、补办、工单、投诉、人工、漏水、宿舍故障、校园卡丢失。
- 知识关键词：选课、课程、考试、成绩、学籍、奖学金、助学金、校园卡、图书馆、报到。
- 问候、自我介绍类：直接进入 `general_chat`。
- 未命中以上关键词：默认进入 `general_chat`，避免随机问题被错误限制在知识库。

路由映射：

```text
knowledge_rag  → knowledge_rag
ticket_handler → ticket_handler
general_chat   → general_chat
```

合规检查虽然不是用户意图的入口，但所有业务分支都会在完成后进入 `compliance_check`。

文件中还保留了一段旧的 LLM 路由代码，但它位于确定性路由返回之后，当前不可达；真正维护路由时应以当前前面的关键词逻辑为准，或者将旧代码清理/重构为显式开关。

### 9.3 图结构

```text
START
  ↓
supervisor_route
  ├─→ general_chat ───┐
  ├─→ knowledge_rag ──┼→ compliance_check → synthesize → END
  └─→ ticket_handler ─┘
```

`MemorySaver` 作为 LangGraph checkpointer 保存图状态，`thread_id` 使用 `session_id`，因此同一会话可以复用图线程上下文。

### 9.4 通用对话 Agent

文件：`agents/general_chat.py`

职责：处理普通聊天、身份介绍、问候和开放式问题。它使用系统提示词要求模型：

- 以用户相同语言回答。
- 不虚构学校正式政策。
- 不声称已经完成实际系统操作。

它把最终文本写入 `sub_results["general_chat"]`，并追加开始/完成两个轨迹节点。

### 9.5 知识库 RAG Agent

文件：`agents/knowledge_rag.py`。

执行分为四步：

1. `rewrite_query`：把口语问题改写成适合检索的查询。
2. `retrieve_documents`：从 `LongTermMemory` 召回最多 5 篇文档。
3. `rerank_documents`：让模型从候选文档中选择最多 3 篇。
4. `generate_answer`：基于选中的上下文生成回答，并要求注明来源。

如果没有找到文档，Agent 会明确告诉用户当前知识库没有直接答案，并建议联系对应部门，而不是强行编造政策。

### 9.6 工单 Agent

文件：`agents/ticket_handler.py`。

它先让模型把用户文本解析成 JSON：

```json
{
  "action": "create|query|update",
  "ticket_type": "dorm_repair|campus_card|...",
  "priority": "low|medium|high|urgent",
  "summary": "摘要",
  "details": "详情",
  "ticket_id": "查询时可选"
}
```

当前支持的工单分类包括宿舍报修、校园卡、奖助学金、教务、投诉、咨询和通用服务。创建工单时生成类似 `CAMP-日期-随机码` 的编号，并保存类型、优先级、状态、摘要、详情、用户和时间。

当前 `TicketStore` 是进程内字典，因此只适合演示和联调；生产环境应替换为 PostgreSQL/MySQL 等持久化存储，并增加用户鉴权和工单权限校验。

### 9.7 合规检查 Agent

文件：`agents/compliance_checker.py`。

它位于所有业务 Agent 之后，执行两层检查：

1. 规则检查：正则识别手机号、身份证号、学号、邮箱，并检查禁止/越权表达。
2. LLM 检查：识别不当承诺、危险指引、绕过正式流程、歧视或不适合校园客服的内容。

规则命中后会生成脱敏文本；高风险或严重风险内容可以使 `compliance_passed` 为 `false`。Supervisor 在汇总时会停止正常业务输出，改为提示用户转人工或走正式流程。

这是一层输出防护，不是完整的安全体系。生产环境仍需在日志、数据库、权限、传输和运维层面做隐私保护。

### 9.8 `intent_router.py` 的位置

`IntentRouterAgent` 提供了独立的 LLM 意图分类能力，适合未来处理更多类别或替换关键词路由。当前 `create_supervisor_graph` 会实例化它，但主图没有把它作为节点接入，因此当前请求主链路仍由 `SupervisorNode.route_decision` 的确定性规则负责。

## 10. 三层记忆

### 10.1 工作记忆

`WorkingMemory` 是进程内的会话级状态，记录当前会话的上下文和最近意图。Supervisor 会写入 `last_intent`，下一次请求可以读取。

适合保存：当前任务状态、最近路由、临时中间结果。它不是跨进程持久化数据库。

### 10.2 短期记忆

`ShortTermMemory` 优先使用 Redis：

- Key 格式：`smartcs:short_term:{session_id}`。
- 使用 Redis List 保存消息。
- 最多保留 `max_turns=20` 条。
- 默认 TTL 为 1800 秒。

Redis 连接失败、Redis 包未安装或 ping 失败时自动切换到进程内字典。回退模式便于本地开发，但多进程部署时每个进程的会话不共享。

### 10.3 长期记忆

`LongTermMemory` 保存知识文档和元数据。启动时 `main.py` 会写入四篇示例文档：选课、宿舍报修、校园卡、奖助学金。

支持：

- 文档新增和批量新增。
- FAISS 索引搜索。
- 索引和元数据保存到磁盘。
- 文本按段落/固定长度分块。
- FAISS 不可用时关键词检索回退。

当前 `_simple_embedding()` 通过文本哈希生成可重复的随机向量，只是为了让接口和演示流程完整。它不能表达真实语义相似度。生产环境应换成真实 Embedding 模型/API，并重新建立索引。

## 11. RAG 知识库如何扩展

可以使用 `LongTermMemory.load_knowledge_base()` 从目录批量加载 `.txt` 文件。基本流程是：

1. 将正式 FAQ、办事指南、通知整理成 UTF-8 文本。
2. 按主题放入知识库目录。
3. 在启动阶段调用批量加载或导入脚本。
4. 用真实 Embedding 生成向量并持久化 FAISS/其他向量库。
5. 在回答中保留来源字段，方便审计和纠错。

正式环境要同时维护文档版本、发布日期、适用学院/校区、失效时间和权限标签，避免旧政策覆盖新政策。

## 12. MCP 风格工具层

`mcp/mcp_server.py` 提供工具定义、注册和调用封装。每个工具包含：

- `name`
- `description`
- `input_schema`
- 异步 handler
- `category`
- `requires_auth` 标记

当前默认工具：

| 工具 | 分类 | 当前行为 |
|---|---|---|
| `campus_card_query` | `student_services` | 返回模拟校园卡状态和余额 |
| `knowledge_search` | `knowledge` | 返回模拟知识片段 |
| `service_ticket_create` | `ticket` | 返回模拟工单编号 |
| `emergency_check` | `safety` | 根据事件关键词做风险分级 |

工具调用会记录成功、失败、耗时和时间戳，可通过 `/api/metrics` 查看最近调用日志。`handle_jsonrpc()` 还提供 `tools/list`、`tools/call` 和 `ping` 的 JSON-RPC 风格处理。

要接入真实系统，应在 handler 内调用教务、后勤或校园卡系统 API，并增加：Token 校验、用户身份映射、超时、重试、幂等、错误码和审计日志。

## 13. 观测、指标和轨迹

### 13.1 OpenTelemetry

`trace_agent_call()` 装饰 Agent 方法，记录：

- Agent 名称。
- 方法名。
- 调用耗时。
- 是否成功。
- 结果字段名或异常信息。

设置 `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317` 后，可将 Trace 发往 Jaeger。没有 OTEL 依赖或没有配置时，业务仍可以运行。

### 13.2 `/api/metrics`

该接口返回 `AgentMetrics` 摘要和最近 20 条工具调用日志。当前代码中 `AgentMetrics` 已提供计数、平均耗时和错误率结构，但 Agent 装饰器没有自动调用 `record_call()`；因此如果没有额外接入记录逻辑，指标统计可能为空，而 OpenTelemetry Span 仍可以存在。

### 13.3 前端轨迹和后端 Trace 的区别

| 内容 | 前端轨迹弹窗 | OpenTelemetry Trace |
|---|---|---|
| 面向对象 | 最终用户 | 开发和运维人员 |
| 内容 | 简短、可读、脱敏的阶段摘要 | 调用耗时、成功率、异常等技术信息 |
| 传输 | `/api/chat` 响应中的 `trace` | OTLP 到 Jaeger 等后端 |
| 是否是模型 CoT | 否 | 否，仍应避免记录私有推理 |

## 14. 常用调试方式

### 14.1 检查服务是否启动

```powershell
Invoke-RestMethod http://localhost:8000/health
```

预期类似：

```json
{"status":"healthy","version":"1.0.0"}
```

### 14.2 检查模型配置状态

```powershell
Invoke-RestMethod http://localhost:8000/api/config
```

`configured` 只表示后端读到了非占位 Key，不代表 Key 一定有效。真正调用是否成功要看 `/api/chat`。

### 14.3 用接口测试随机问题

```powershell
$body = @{ message = '请帮我解释一下人工智能和机器学习的区别' } | ConvertTo-Json
Invoke-RestMethod http://localhost:8000/api/chat -Method Post -ContentType 'application/json' -Body $body
```

未命中校园关键词的问题会进入 `general_chat`，不会被强制限制为固定 FAQ。

### 14.4 测试校园知识问题

```powershell
$body = @{ message = '校园卡丢失后应该怎么办？' } | ConvertTo-Json
Invoke-RestMethod http://localhost:8000/api/chat -Method Post -ContentType 'application/json' -Body $body
```

预期 `intent` 通常为 `knowledge_rag`，响应中会包含知识库来源或无结果提示。

### 14.5 测试工单问题

```powershell
$body = @{ message = '宿舍漏水，请尽快安排报修' } | ConvertTo-Json
Invoke-RestMethod http://localhost:8000/api/chat -Method Post -ContentType 'application/json' -Body $body
```

预期 `intent` 为 `ticket_handler`，并生成一个内存工单编号。

## 15. 常见问题与排错

### 页面打不开

确认启动目录是 `python-impl`，命令是 `python -m api.main`，并检查 `8000` 端口是否被占用。也可以设置 `PORT=8001` 后访问 `http://localhost:8001`。

### `configured=false`

检查 `python-impl/.env` 是否存在、变量名是否拼写为 `DEEPSEEK_API_KEY`，以及是否仍是 `sk-your-deepseek-api-key` 占位值。修改后要重启服务。

### 有 Key 但回答仍是 fallback

检查 Base URL 是否包含正确的 `/v1` 路径、模型名是否有效、网络是否可访问，并查看 `server.err.log` 或终端异常。客户端遇到 HTTP 错误会主动回退，所以前端仍可能显示可用但质量较低的演示回答。

### Redis 连接失败

本地直接启动时没有 Redis 也可以运行，系统会使用内存回退。若需要多进程共享会话或重启后保留短期历史，应启动 Redis 并确认 `REDIS_URL`。

### RAG 结果不准确

首先确认问题命中了知识路由；其次检查知识文档是否被加载。当前哈希向量不是语义向量，生产环境必须替换真实 Embedding。还应增加文档版本和检索评测。

### 工单重启后消失

这是当前设计：`TicketStore` 是内存字典。接入数据库后，需要把创建、查询、更新、状态流转和权限校验放在持久化服务中。

### 轨迹一次性出现

这是当前同步接口的预期行为：后端先完成整次请求，前端收到结果后播放轨迹。想要真正边执行边展示，需改用 SSE/WebSocket 或 LangGraph streaming。

## 16. 安全注意事项

- 真实 API Key 只放在本地 `.env`、部署平台 Secret 或密钥管理系统中，不要写入文档、README、前端代码、日志或 Git。
- 前端不应直接调用 DeepSeek，所有模型请求都应由后端代理。
- `/api/config` 只能返回布尔状态和非敏感配置。
- 生产环境关闭 `allow_origins=["*"]`，改为明确的前端域名。
- 为 `/api/chat`、`/api/tools/call` 添加登录、权限和限流。
- 工具调用前校验用户身份和参数，尤其是校园卡、成绩、学籍和工单操作。
- 不要把完整用户输入、身份证号、手机号或模型提示词写入普通日志。
- 合规 Agent 是辅助防护，不能替代正式的隐私、内容安全和人工审核体系。

## 17. 推荐的生产化路线

按优先级建议：

1. 把工单从内存迁移到 PostgreSQL/MySQL，并增加用户认证和状态流转。
2. 用真实 Embedding 模型替换 `_simple_embedding()`，完善 FAISS 或迁移到 Milvus/pgvector。
3. 给知识文档增加版本、权限、来源和有效期，建立离线评测集。
4. 将 `/api/chat` 改成 SSE/WebSocket，后端实时推送 Agent 状态事件。
5. 将 MCP handler 接入真实校园系统，增加超时、重试、幂等和审计。
6. 清理前端重复事件监听和源码中的历史乱码，补充前端错误状态和网络重连。
7. 完善 OpenTelemetry 指标记录、日志关联 ID、告警和成本统计。
8. 增加单元测试、API 集成测试、路由测试、合规测试和 RAG 召回评测。
9. 增加容器健康检查、非 root 用户、生产 CORS、HTTPS 和密钥轮换。

## 18. 维护者阅读顺序

第一次阅读代码时建议按下面顺序：

1. 先看 `frontend/index.html`，理解浏览器发送什么请求、如何保存会话和显示轨迹。
2. 再看 `api/main.py`，掌握应用启动、接口和 `graph.ainvoke()` 入口。
3. 阅读 `agents/supervisor.py`，理解状态字段、路由和图结构。
4. 分别阅读 `general_chat.py`、`knowledge_rag.py`、`ticket_handler.py`、`compliance_checker.py`。
5. 阅读 `llm_client.py`，理解所有 Agent 如何共享 DeepSeek 兼容客户端。
6. 阅读三类 memory，理解会话上下文、消息历史和知识文档的生命周期。
7. 最后阅读 `mcp_server.py`、`otel_config.py` 和 Docker 文件，了解扩展点和部署方式。

## 19. 一句话总结

本项目是一个可以直接运行的校园客服多 Agent 原型：前端负责交互和可视化，FastAPI 负责服务边界，LangGraph 负责 Agent 协作，DeepSeek 负责语言生成，RAG 负责知识依据，工单 Agent 负责结构化服务，合规 Agent 负责输出防护，Redis/FAISS/MCP/OpenTelemetry 分别提供记忆、检索、工具和观测能力。

