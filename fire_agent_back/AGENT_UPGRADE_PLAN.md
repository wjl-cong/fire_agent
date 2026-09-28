# 焰哨多 Agent 平台 — Agent 技术升级规划方案

> 制定日期：2026-09-27（v2：补充招聘市场对标 + 难点/创新点）
> 依据：全量代码走读（后端 ~4.6k 行 / 前端 ~9.6k 行）+ 2025–2026 Agent 技术调研 + 15+ 份真实 JD 调研（腾讯/字节/猎聘/BOSS）
> 原则：**够用就好，能 workflow 不 agent；每一项技术必须对应真实痛点，不为实现而实现**

---

## 一、现状诊断：当前 Agent 架构的真实差距

当前实现（[orchestrator_agent.py](fire_agent_back/app/agents/orchestrator_agent.py)）是 **LangGraph 固定五节点串联**：

```
parse_task → query_data → analyze_gis → retrieve_knowledge → generate_report
```

对照业界标准，存在以下结构性差距（按严重度排序）：

| # | 现状问题 | 具体表现 | 后果 |
|---|---------|---------|------|
| 1 | **计划与执行脱节** | `parse_task` 让 LLM 拆解了 plan，但 `should_continue` 只按 status 走固定链，**plan 完全没有参与路由** | "编排"名不副实，用户问"查个数据"也硬跑全流程 5 步，浪费 token 和时间 |
| 2 | **无 checkpoint 持久化** | `graph.invoke()` 无 checkpointer，无 thread_id | 任务中断即丢失；无法实现 HITL、断点续跑、多轮对话 |
| 3 | **假流式** | 前端 agent-center 用 600ms 定时器模拟步骤动画；后端执行是同步阻塞 HTTP | 30s+ 长任务有超时风险；用户看到的进度是假的 |
| 4 | **检索全量内存计算** | `rag_service.retrieve()` 把用户**所有** chunks 读进 Python 逐条算余弦 | 文档多了必崩；embedding 存 JSON 文本，无索引 |
| 5 | **LLM 输出裸解析** | `json.loads(text.strip().removeprefix("```json"))` 裸解析 plan | 模型输出稍微变形就 fallback，鲁棒性差 |
| 6 | **无重试/熔断/降级** | LLM 调用失败直接进 except → 模板报告 | 百炼限流/网络抖动时体验断崖式下降 |
| 7 | **无人工介入点** | 报告生成即落库发布 | 高风险扑救建议没有审批闸口 |
| 8 | **无评估与观测** | 无 trace、无 token 记账、无质量回归 | 改 prompt/换模型 = 盲改 |
| 9 | **节点串行** | query_data 与 retrieve_knowledge 无依赖关系却串行执行 | 端到端延迟白白翻倍 |
| 10 | **无自我修正** | 数据查询为空、检索未命中时无反思重试 | "no_data" 直接传导到报告，产出空洞报告 |

---

## 二、调研结论：用什么、不用什么

### 采用（与痛点一一对应）

| 技术 | 解决痛点 | 依据 |
|------|---------|------|
| **Supervisor 模式 + plan 驱动路由** | #1 | Anthropic《Building effective agents》orchestrator-workers；langgraph-supervisor 已 GA |
| **PostgresSaver checkpoint** | #2 | LangGraph 1.0 官方持久化方案，与现有 PG 同库零新组件 |
| **SSE + graph.astream** | #3 | LangGraph stream_mode=["updates","messages"]，FastAPI 原生 SSE |
| **并行分支（fan-out/fan-in）** | #9 | query_data ∥ retrieve_knowledge 无依赖，直接并行 |
| **Evaluator-optimizer（报告评审循环）** | #10 报告质量 | Anthropic 模式之一，高风险输出值得生成-评审循环 |
| **with_structured_output** | #5 | LangChain 标准能力，百炼 OpenAI 兼容端点原生支持 |
| **pgvector + HNSW + RRF + qwen3-rerank** | #4 | 与业务数据同库；注意 **gte-rerank 已下线，必须用 qwen3-rerank** |
| **Adaptive RAG 路由** | #4 复杂查询 | 简单查询直通，复杂查询进"改写→检索→评分→重检"环（max_steps=3） |
| **interrupt + Command(resume) HITL** | #7 | LangGraph 原生；报告发布前人工审批 |
| **统一 LLM 调用层：重试→熔断→降级链** | #6 | 指数退避 → pybreaker 熔断 → aliyun→amd→模板降级 |
| **Langfuse 私有化 + token 记账** | #8 | 开源可私有化（数据敏感不出内网），OTel 原生 |
| **输出护栏：引用强制校验** | 报告可信度 | 关键数字必须能溯源到 data_results，校验不过 REASK 重生成 |

### 明确不采用（工程边界）

| 技术 | 不采用原因 |
|------|-----------|
| A2A 协议 | 单系统内部多 Agent，LangGraph handoff 足够；A2A 是跨组织协议，生产采用仅 150+ 组织，留作未来跨系统对接选项 |
| 更换框架（CrewAI/AutoGen/Swarm） | AutoGen 已进入维护模式（2025.10）；LangGraph 1.0 GA 且现有投资可全部保留 |
| Network/swarm 对等拓扑 | 难调试、不可观测；supervisor 分层是本系统正确形态 |
| mem0 | 用 LangGraph 官方 LangMem + PostgresStore，避免引入第二个记忆栈 |
| E2B 代码沙箱 | 当前无 LLM 动态执行代码需求；SQL 查询走参数化仓储层，不开放 text-to-SQL |
| 语义分块 | 收益有限；防火规范类文档按条款结构切分性价比更高 |
| Query Decomposition 多跳 | 4–10× 成本，本平台无多跳问题场景，不引入 |

---

## 三、目标架构

```
                        ┌─────────────────────────────────────────┐
                        │           Supervisor (Orchestrator)      │
                        │  parse_task → 真实 plan 驱动条件路由      │
                        └───────┬───────────────┬─────────────────┘
                                │ plan 决定执行哪些子图
            ┌───────────────────┼───────────────────┐
            ▼ (并行 fan-out)     ▼                   ▼
   ┌─────────────────┐  ┌───────────────┐   ┌────────────────┐
   │ DataAgent 子图   │  │ RagAgent 子图  │   │ GisAgent 子图   │
   │ 历史+预测双源查询 │  │ Adaptive RAG: │   │ 聚类/风险识别   │
   │ 空结果→反思重试  │  │ 改写→检索→    │   │                │
   │                 │  │ 评分→重检(≤3) │   │                │
   └────────┬────────┘  └───────┬───────┘   └───────┬────────┘
            └───────────────────┼───────────────────┘
                                ▼ (fan-in 汇聚)
                    ┌───────────────────────┐
                    │ ReportAgent 生成       │
                    └───────────┬───────────┘
                                ▼
                    ┌───────────────────────┐
                    │ Reviewer 评审节点      │── 不通过(≤2轮) ──▶ 回到 ReportAgent
                    │ 引用强制+事实核验护栏   │
                    └───────────┬───────────┘
                                ▼
                    ┌───────────────────────┐
                    │ interrupt() 人工审批   │── approve/edit/reject
                    └───────────┬───────────┘
                                ▼
                          报告落库发布

横切能力：PostgresSaver checkpoint │ SSE 事件流 │ Langfuse trace │ 统一LLM调用层(重试/熔断/降级)
```

---

## 四、分期实施计划

### P0 — 工程地基（先做，全是低风险高收益）

**目标：修掉"假"的部分，不动架构。**

1. **SSE 真实流式** `[后端+前端]`
   - 后端：`POST /agent/tasks` 改为立即返回 task_id，新增 `GET /agent/tasks/{id}/stream`（SSE，`graph.astream(stream_mode="updates")` 桥接为节点进度事件）
   - 前端 agent-center：删掉 600ms 假动画，EventSource 消费真实节点事件
   - 验收：任务执行中前端步骤状态与后端节点严格一致；断网重连用 Last-Event-ID

2. **结构化输出替代裸解析** `[后端]`
   - `parse_task` 改用 `llm.with_structured_output(PlanSchema)`（Pydantic: `plan: list[SubTask]`）
   - 同步治理所有 `json.loads(resp.content)` 点（query_service.parse 等）
   - 验收：构造 20 条变形输出测试，解析成功率 100%

3. **统一 LLM 调用层** `[后端]`
   - 新文件 `app/core/llm_invoker.py`：封装 invoke，内置指数退避重试（限流/超时，最多3次）→ pybreaker 熔断 → 降级链（当前 provider → 备用 provider → 模板）
   - 每次调用记 token 用量到 `agent_task_steps` 新列
   - 所有 agent/service 的 `llm.invoke` 收编到该层
   - 验收：停掉百炼 key，系统自动切 AMD 并在 steps 中标注降级

4. **PostgresSaver checkpoint** `[后端]`
   - `graph.compile(checkpointer=PostgresSaver(conn))`，thread_id = task_id
   - 任务中断/服务重启后可从最近节点续跑
   - 为 P1 的 HITL 铺路
   - 验收：执行中重启 uvicorn，任务恢复完成

### P1 — 架构升级（核心改造）

5. **Supervisor 真编排：plan 驱动路由** `[后端]` —— 解决痛点 #1
   - `should_continue` 改为读 `parsed_intent.plan` 动态路由：plan 里没有的节点跳过（如纯查数不跑 RAG，纯知识问答不查库）
   - `parse_task` prompt 增加 few-shot，plan schema 加 `required: bool` 与 `reason` 字段（可解释性，前端展示"为什么跳过某 Agent"）
   - 验收：问"森林防火条例有哪些"只走 RAG 节点；问"查2024年昆明火点"跳过 RAG

6. **并行 fan-out/fan-in** `[后端]` —— 解决痛点 #9
   - query_data ∥ retrieve_knowledge 并行分支，analyze_gis 依赖 query_data 结果，generate_report 等全部汇聚
   - 验收：端到端延迟下降 ≥30%

7. **DataAgent 反思重试** `[后端]` —— 解决痛点 #10
   - query_data 结果为空时进入 retry 子节点：LLM 分析为何为空（年份超范围？城市名未匹配？）→ 放宽参数重查，最多 2 轮
   - 仍为空则在 steps 明确标注原因，报告节点据此如实说明（现有约束保留：数据为 0 必须说明原因）
   - 验收："2027年火点"类查询不再产出空洞报告

8. **Evaluator-optimizer 报告评审循环** `[后端]`
   - 新增 reviewer 节点（低温度）：按检查单评审——数字是否与 data_results 一致（引用强制）、结构完整性、每州市建议覆盖
   - 不通过 → 带评审意见回 ReportAgent 重写，最多 2 轮后强制放行并标注
   - 护栏：报告中关键数字正则回溯 data_results，对不上即不通过
   - 验收：评审拦截率可统计；两轮后报告数字 100% 可溯源

9. **pgvector 迁移 + 检索升级** `[后端+DB]` —— 解决痛点 #4
   - `kb_chunks.embedding`: Text(JSON) → `vector(1024)`，HNSW 索引（m=16, ef_construction=64, cosine ops）
   - 迁移脚本：读现有 JSON 向量批量写入新列
   - 检索 SQL 化：向量 Top60 + 关键词 Top60 → RRF 融合（k=60）→ **qwen3-rerank** 精排取 Top5（百炼 OpenAI 兼容 `/reranks`）
   - 保留现有 bigram 兜底与"未命中明确告知"契约（项目硬性约束）
   - 验收：1000+ chunks 检索 <500ms；命中质量人工抽检优于现状

10. **Adaptive RAG 路由** `[后端]`
    - RagService 入口加轻量难度判断（规则+小模型）：事实直给 → 现有混合检索直通；模糊/复杂 → "查询改写→检索→评分→重检"环，max_steps=3
    - 验收：简单问题延迟不增加；换说法提问命中率提升

11. **HITL 报告审批** `[后端+前端]` —— 解决痛点 #7
    - generate_report 后 `interrupt()` 暂停，任务状态 `awaiting_approval`
    - 前端 agent-center 出现审批卡片：预览报告 + approve/edit/reject 三操作 → `POST /agent/tasks/{id}/resume` 携带 `Command(resume=...)`
    - approve → 落库发布；edit → 人工修改稿直接落库；reject → 带意见回 ReportAgent
    - admin 配置项：`AGENT_REQUIRE_APPROVAL`（默认开）
    - 验收：审批前报告不进报告中心；审批动作进审计日志

### P2 — 生产化与生态（价值增强，按优先级选做）

12. **Langfuse 私有化观测** `[后端+运维]`
    - Docker 起 Langfuse，LangChain callback 接入；trace_id 贯穿 SSE 事件与系统日志
    - 看板：每任务 token 成本、节点耗时、降级率、评审拦截率

13. **评估回归体系** `[后端]`
    - 从生产 trace 沉淀 50 条 golden set（真实查询+期望要点）
    - DeepEval（trajectory 指标：Task Completion / Tool Correctness）+ RAGAS（Faithfulness）跑回归
    - 改 prompt/换模型前必跑，进 CI

14. **MCP 工具化数据源** `[后端]` —— **JD 高频项（2026 年 ~60% 的 JD 明确要求），建议从 P2 提前至 P1 末**
    - 把高德天气、（未来）实时火情 API 封装为 MCP server（FastMCP），agent 侧 langchain-mcp-adapters 接入
    - 边界：仅只读数据源 MCP 化；数据库访问仍走仓储层，不开放 text-to-SQL

15. **LangMem 长期记忆** `[后端]` —— JD 高频项"短期+长期记忆模块"
    - PostgresStore 存用户分析偏好（常查州市、关注时段），按 user_id namespace 隔离
    - ReportAgent 生成时注入偏好，报告更贴合用户辖区
    - 严格遵从现有用户数据隔离硬约束

16. **Docker 化交付** `[运维]` —— JD 高频项（~60% 要求 Docker/K8s）
    - 编写后端/前端/Langfuse 的 docker-compose 编排，一键拉起全栈
    - .env 模板化、健康检查端点、结构化 JSON 日志
    - K8s 不做（单机/小规模部署场景，过度工程）

17. **进度体验优化（节点级实时进度）** `[后端+前端]` —— 解决 P0 上线后暴露的观感问题："点击后静默数秒 → 前 4 步瞬间全打勾 → 报告长时间转圈"
    - 根因：进度事件只在节点完成时产生（stream_mode="updates" 语义），5 个节点耗时极不均匀（parse_task LLM 意图解析最慢、generate_report 次之），节点粒度进度条必然"跳格"
    - 节点开始事件：worker 在节点入口写一条 `status=running` 的步骤行，SSE 增量推送；前端转圈时机从"上一步完成"提前到"当前步真正开始"，pending→running→completed 三态完整
    - parse_task 轻量化：意图解析切换更快小模型（或降 max_tokens、温度），缩短首事件前的静默窗口
    - 边界：不改变"DB 为唯一事实源"的断线重放机制

18. **全链路流式输出（内容级）** `[后端+前端]` —— 所有面向用户的 LLM 生成内容统一"有什么内容就输出什么内容"，消灭干等整段返回
    - **llm_invoker 新增流式通道** `stream_llm()`：与 invoke_llm 同级（复用重试/熔断/降级链），async generator 逐 chunk yield；invoke_structured（意图解析/任务拆解）保持非流式，结构化输出不流式
    - **Agent 报告流式**：generate_report 改 stream 生成，SSE 增量推 `type=report_delta` 帧，agent-center 报告区打字机式边生成边渲染（Markdown 增量渲染）
    - **RAG 问答流式**：`/rag/ask` 增加 SSE 变体（如 `/rag/ask/stream`），答案逐 token 返回，知识库页面对接；来源引用在流结束后附上，未命中提示逻辑不变
    - **智能查询摘要流式**：query_service 的摘要生成同步改流式，smart-query 摘要 tab 实时出字
    - **边界**：流式中断的半截内容不落库（半成品不污染历史），终态仍以完整内容落库（报告 upsert_from_task、问答 result JSON），保持 DB 唯一事实源与断线重放语义；流式与 P2#17 的节点进度事件共用同一条 SSE 连接，不重复建连

---

## 五、风险与注意事项

| 风险 | 应对 |
|------|------|
| pgvector 迁移期间检索中断 | 双写过渡：新列回填完成前保留 JSON 读取路径，切换后删旧列 |
| qwen3-rerank 计费 | 只对 Top60 候选精排，单次成本可忽略；加结果缓存（同 query+同文档集 5min） |
| HITL 打断现有"一键出报告"体验 | 配置开关 `AGENT_REQUIRE_APPROVAL`，报告中心来源标记区分已审/未审 |
| 并行节点共享 db session | 每节点独立 session（SessionLocal 工厂注入），禁止跨线程复用 |
| Langfuse 私有化资源开销 | 独立容器，采样率可配；不通过则降级为纯日志 |
| 思考链模型（enable_thinking）与 SSE | reasoning_content 与 content 分流渲染，前端单独折叠区展示 |
| 项目硬约束回归 | 每期验收必查：双表双源查询、软删除语义、报告署名、用户隔离、.env 热生效、脱敏显示 |

## 六、工作量与依赖总览

| 阶段 | 项 | 依赖 | 影响面 |
|------|----|------|--------|
| P0 | SSE / 结构化输出 / LLM调用层 / checkpoint | 无 | routes/agent.py、orchestrator、core/llm.py、agent-center前端 |
| P1 | 路由/并行/反思/评审/审批 | P0 全部 | orchestrator 重构、新增 reviewer 节点、admin 配置 |
| P1 | pgvector + rerank + Adaptive RAG | DB 扩展安装 | rag_service.py、kb 模型、迁移脚本 |
| P2 | Langfuse / 评估 / MCP / 记忆 / Docker | P1 完成 | 新增基础设施，不动核心链路 |
| P2 | 进度体验优化 + 全链路流式输出（#17/#18） | P0 SSE 完成 | llm_invoker、routes/agent.py+rag/query 路由、agent-center/knowledge-base/smart-query 前端 |

**关键原则贯穿始终**：每一期结束系统都是完整可用的；所有新能力都有配置开关可回退；不破坏项目记忆中的任何硬性约束。

---

## 七、招聘市场对标：80% JD 覆盖分析

基于 2025–2026 年 15+ 份真实 JD（腾讯/字节官网、猎聘、BOSS直聘、智联）调研，JD 高频要求与本项目覆盖映射：

### 7.1 覆盖度对照表

| JD 高频要求（出现率） | 本项目对应实现 | 状态 |
|---|---|---|
| Python + asyncio 异步 + FastAPI（~100%） | 全栈 FastAPI，asyncio_run 协程桥接 | ✅ 已有 |
| LangGraph / 多 Agent 状态机编排（~90%） | Supervisor 五节点 StateGraph → P1 升级 plan 驱动路由 + 子图 | ✅ 已有并强化 |
| RAG 全链路：解析→分块→向量化→检索→生成（~90%） | PDF 四层提取回退 OCR + 结构分块 + pgvector 迁移 | ✅ 已有并强化 |
| Function Calling / Tool Use（~85%） | P0 结构化输出（with_structured_output）+ P2 MCP 工具接入 | ⚠️ 补齐 |
| Prompt 工程体系化：CoT/ReAct/Few-shot/结构化输出（~85%） | few-shot plan prompt、ReAct 反思重试、结构化输出、prompt 版本化 | ⚠️ 补齐 |
| 向量数据库（Milvus/pgvector/Qdrant 任一，~80%） | pgvector + HNSW（P1-9） | ⚠️ 补齐 |
| 混合检索 BM25+向量 + Reranker（高频） | 关键词分（承担 BM25 角色）+ 向量 + RRF + qwen3-rerank（P1-9/10） | ⚠️ 补齐 |
| MCP 协议（~60%，增速最快） | P1末/P2-14 FastMCP 封装数据源 + langchain-mcp-adapters | ⚠️ 补齐 |
| 多 Agent 协作 Supervisor/Hierarchical（~60%） | 现架构即 Supervisor，P1 强化为真编排 | ✅ 已有并强化 |
| Docker / 部署交付（~60%） | P2-16 docker-compose 全栈编排 | ⚠️ 补齐 |
| SSE/WebSocket 流式输出（~40%） | P0-1 SSE + graph.astream + Last-Event-ID 断线续传 | ⚠️ 补齐 |
| 评测体系 RAGAS/DeepEval/LLM-as-Judge（~40%，大厂近必选） | P2-13 golden set + DeepEval trajectory + RAGAS Faithfulness | ⚠️ 补齐 |
| 记忆模块：短期+长期记忆、会话持久化 | P0-4 PostgresSaver（短期/thread）+ P2-15 LangMem（长期/语义） | ⚠️ 补齐 |
| HITL 人工介入 | P1-11 interrupt + approve/edit/reject | ⚠️ 补齐 |
| 容错：超时/重试/熔断/降级/护栏 | P0-3 统一 LLM 调用层 + P1-8 引用强制护栏 | ⚠️ 补齐 |
| Token 成本控制 / 多模型路由 | P0-3 token 记账 + aliyun/amd/ollama 三 provider 路由（现有） | ✅ 已有并强化 |
| 可观测：Langfuse/LangSmith、Trace | P2-12 Langfuse 私有化 + trace_id 贯穿 | ⚠️ 补齐 |
| 多模态（VLM/ASR/TTS，加分项） | 已有：Qwen-VL 火情识别 + 百炼 ASR/TTS 语音交互 | ✅ 已有（差异化） |
| 微调 LoRA/SFT（~30%，多为加分） | 不做。API 型项目无训练基础设施，JD 中该要求多为加分项非硬性 | ❌ 明确不做 |

**结论**：现状约覆盖 **60%**；完成 P0+P1 后达 **80%**；完成 P2 后达 **~90%**（仅差微调/推理部署两个加分专项，属另一岗位方向）。

### 7.2 简历写法建议（对应 JD 偏好：Action + 技术细节 + 量化结果）

完成升级后，项目可按以下口径描述（数字为示例，以实际压测为准）：

> **焰哨多 Agent 森林火险分析平台**（Python / FastAPI / LangGraph / pgvector / Vue3）
> - 设计 Supervisor 模式多 Agent 编排（Query/Data/Gis/RAG/Report 5 智能体），LLM 动态规划驱动条件路由，支持节点级并行 fan-out，端到端延迟降低 30%+
> - 基于 LangGraph PostgresSaver 实现任务级 checkpoint 与 interrupt 人工审批（HITL），长任务支持断点续跑与 SSE 实时进度推送（Last-Event-ID 断线续传）
> - 构建混合检索 RAG：pgvector HNSW 向量召回 + 中文关键词召回 + RRF 融合 + qwen3-rerank 精排，检索准确率 xx%→xx%（评测集实测）
> - 统一 LLM 调用层：指数退避重试 + 熔断 + 多 provider 降级链（百炼/AMD GPU 云/本地 Ollama），可用性 99.x%
> - 建立评测闭环：50 条 golden set + DeepEval trajectory 指标 + RAGAS Faithfulness，prompt/模型变更回归门禁
> - 多模态能力：Qwen-VL 火灾图像识别 + ASR/TTS 语音交互，MCP 协议接入外部气象数据源

---

## 八、项目难点与创新点（面试/答辩可直接使用）

### 8.1 项目难点（难点 = 真实踩过的坑 + 工程取舍）

**难点 1：双源异构数据的统一查询与时间重叠处理**
- 问题：历史火点表（2021-2025，NASA FIRMS 点数据）与预测火险表（2025-2026，GTWR 模型格点数据）schema 完全不同、坐标粒度不同、2025 年数据重叠
- 解法：DataAgent 双表并行查询 + `source` 标签溯源 + 预测数据无坐标时州市中心点兜底；GisAgent 对两源分别采用不同算法（历史 0.1° 网格聚类 / 预测 risk_score≥3 等级识别）再合并热点
- 工程价值：避免"以历史充预测"或"2025 年数据丢失"两类隐性错误，报告强制标注各源覆盖量

**难点 2：GB/T 国家标准 PDF 的文字层乱码**
- 问题：国家标准全文公开系统的 PDF 使用自定义字体编码，pdfplumber/pypdf/PyMuPDF 提取均为乱码（U+7280-72FF 生僻字形替代中文），导致 RAG 检索全失效
- 解法：乱码启发式检测（生僻字密度>3% 或 标点密度>35%且中文<35%）→ 四层提取回退链 → RapidOCR 离线图像识别兜底（2x 渲染保证小字号识别率，限 60 页防超时）
- 工程价值：不引入在线 OCR API（数据不出内网），纯 ONNX 本地推理

**难点 3：无 LLM / LLM 异常时的服务连续性**
- 问题：模型限流、key 过期、provider 抖动都会让"智能"功能整体不可用
- 解法：三层防线——统一调用层（重试→熔断→跨 provider 降级链）→ 节点级 try/except → 无 LLM 时的规则兜底（模板报告仍含真实数据、关键词检索不需要向量、模板意图解析）
- 工程价值：系统在任何单点故障下"降级不瘫痪"，每个降级动作在 steps 中可见可审计

**难点 4：报告数字的防幻觉强制约束**
- 问题：LLM 写报告喜欢编数字，防火报告数字错了是事故
- 解法：评审节点把报告中的关键数字正则回溯 data_results/gis_results，对不上即 REASK 重写（≤2 轮）；prompt 层要求"所有数字必须直接引用、数据为 0 必须说明原因"
- 工程价值：从"提示词约束"升级为"程序化校验"，引用强制护栏

**难点 5：软删除语义下双中心的数据一致性**
- 问题：Agent 任务历史与报告中心要完全独立——用户自删报告（hidden）不影响任务记录，管理员删（deleted）全局不可见，但任务详情仍要能回看报告
- 解法：报告表 hidden/deleted 双标记位 + 任务表 report_id 永不置空 + 任务详情查询 include_deleted=True
- 工程价值：用户隐私、管理审计、历史追溯三个互相冲突的需求同时满足

**难点 6：同步 SQLAlchemy + 异步 Agent + FastAPI 事件循环的协程冲突**
- 问题：LangGraph 节点是同步函数，但 GisAgent/RagAgent 是 async，在 FastAPI 事件循环内直接 asyncio.run 会抛 "event loop already running"
- 解法：asyncio_run 检测运行中 loop → 有则 ThreadPoolExecutor 单线程另起循环执行；P1 并行化时各节点注入独立 session，禁止跨线程复用
- 工程价值：不引入重型任务队列（Celery）的前提下解决协程嵌套，保留后续升级 ARQ 的接口位

### 8.2 项目创新点（创新 = 别人没做或做得浅的）

**创新 1：历史+预测双时间轴的 Agentic 火险研判**
- 多数火险系统只有历史统计**或**只接预测模型输出；本平台 DataAgent 将 NASA FIRMS 历史观测与 GTWR 时空预测统一为带 `source` 标签的同构流，Agent 在**同一次推理**中同时引用过去规律与未来风险，报告自动说明各源覆盖边界
- 差异化点：预测数据不是静态展示，而是进入 Agent 推理链路参与巡防建议生成（分时段、分区域、可落地）

**创新 2：面向中文公文场景的"可审计报告"生成管线**
- Evaluator-optimizer 评审循环 + 数字回溯护栏 + 强制来源引用 + 固定署名页脚 + HITL 人工审批闸口，构成公文级可信度链条
- 差异化点：不是"LLM 写个像报告的文本"，而是每个数字可溯源、每次发布有审批记录、每轮重写有评审意见的**责任闭环**——这是政务/应急场景的核心诉求

**创新 3：多模态入口融合的应急指挥体验**
- 视觉（Qwen-VL 火情图像识别）+ 语音（ASR 语音提问 / TTS 播报）+ 地图（OpenLayers 聚合/热力/风险填色）三通道汇聚到同一个 Agent 编排引擎
- 差异化点：一线巡护人员拍照即识别、动口即查询，指挥大屏同步呈现 Agent 分析过程——多模态不是炫技，是火场场景的真实交互刚需

**创新 4：国产化+多云可切换的大模型接入层**
- 百炼（主力）/ AMD GPU 云（国产化算力）/ Ollama（纯离线）三 provider 热切换，模型目录**实时抓取**官方页面（百炼计费文档 / AMD tokenfactory）拒绝硬编码，额度快照静态维护
- 差异化点：embedding 固定百炼、视觉可切、ASR/TTS 固定百炼的细粒度路由策略；配置写 .env 热生效免重启；敏感 key 脱敏显示——一套生产级的"模型运营"体系而非简单 API 调用

**创新 5（升级后）：以 MCP 为边界的工具生态 + 完整评测飞轮**
- 数据源 MCP 化（气象/火情 API 即插即用）+ golden set 回归 + LLM-as-Judge + Langfuse trace，形成"开发→评测→归因→优化"闭环
- 差异化点：多数个人项目止步于"能跑"，本项目具备大厂 JD 中要求的 Harness/Eval 工程能力雏形

---

## 九、一页纸总结

| 维度 | 内容 |
|------|------|
| **现状** | LangGraph 固定五节点串联，覆盖 JD 高频要求 ~60% |
| **P0 工程地基** | SSE 真实流式 / 结构化输出 / 统一 LLM 调用层（重试熔断降级）/ PostgresSaver checkpoint |
| **P1 架构升级** | plan 驱动路由 / 并行 fan-out / DataAgent 反思重试 / 报告评审循环+引用护栏 / pgvector+RRF+qwen3-rerank / Adaptive RAG / HITL 审批 |
| **P2 生产化** | Langfuse 观测 / DeepEval+RAGAS 评测 / MCP 工具化 / LangMem 记忆 / Docker 交付 |
| **完成后 JD 覆盖** | **~90%**（仅差微调/推理部署专项） |
| **明确不做** | A2A、换框架、swarm 拓扑、mem0、代码沙箱、text-to-SQL 开放、K8s、微调 |
| **核心壁垒** | 双源时序 Agentic 研判、可审计公文报告链、多模态应急交互、国产化多云模型运营 |
