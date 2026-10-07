# 焰哨 FlameSentry · 智慧火险预警与多智能体协作平台 —— 后端（fire_agent_back）

> **当前版本：v1.0.1**（P0 可靠性底座 + P1 编排升级 + P2 工程化模块，详见《[整体实现.md](./整体实现.md)》第 13 章 changelog）
> 本项目是「焰哨 FlameSentry · 智慧火险预警与多智能体协作平台」（现实使用名：**焰哨多Agent与可视化平台**）的后端部分，基于 **FastAPI + PostgreSQL/PostGIS + LangChain + LangGraph** 构建。
> 配套前端：[fire_agent_front](https://gitee.com/wjl2004/fire_agent_front)（Vue3 + OpenLayers + ECharts）
> 完整的系统设计文档见本仓库《[整体实现.md](./整体实现.md)》。
> **在线演示**：https://wjl2004.ffuf.cn/（手机上可能会把这个网址ban掉）    or     https://8.156.67.47/login
> **演示账户**：test   123456
> **GitHub 仓库**：https://github.com/wjl-cong/fire_agent（⭐ 欢迎 Star）

---

## 目录

1. [项目简介](#1-项目简介)
2. [技术栈](#2-技术栈)
3. [项目结构](#3-项目结构)
4. [核心功能详解](#4-核心功能详解)
5. [数据库设计](#5-数据库设计)
6. [API 接口总表](#6-api-接口总表)
7. [环境要求](#7-环境要求)
8. [快速启动](#8-快速启动)
9. [数据导入](#9-数据导入)
10. [配置说明（.env）](#10-配置说明env)
11. [常见问题](#11-常见问题)

---

## 1. 项目简介

后端为前后端分离架构的 API 服务，提供以下核心能力：

| 模块              | 核心能力                                                                                                                                                                          |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 认证 auth         | JWT（HS256，24h）注册/登录，bcrypt 密码哈希，admin/user 双角色，用户数据隔离                                                                                                      |
| 大屏 dashboard    | 历史火点（5411 条 NASA FIRMS）/ 预测火险（GTWR 模型）/ 摘要统计（Top5 城市）                                                                                                      |
| 智能查询 query    | 自然语言 → LLM·关键词双引擎意图识别 → 结构化查询 → 摘要/表格/图表/GeoJSON 四维结果，历史落库去重                                                                              |
| 知识库 rag        | PDF/TXT/MD 上传 → 四层文本提取（含 OCR 扫描版）→ 中文感知切分 → 向量化 → 混合检索 + **Rerank 精排（qwen3-rerank，失败降级 RRF）** → LLM 引用来源回答，支持 **/ask/stream SSE 流式**与复杂查询自适应改写 |
| Agent 协作 agent  | LangGraph StateGraph 8 节点编排（**并行 fan-out/join + 评审循环 + HITL 审批**），任务异步执行 + **SSE 节点级实时进度**，步骤/任务/报告落库（支持历史回放），报告七章刚性模板自动生成 |
| 报告 reports      | 报告 CRUD + 导出 Markdown / HTML（打印模板）                                                                                                                                      |
| 视觉与语音 vision | **AI 火情图像识别**（qwen-vl 多模态，四段结构化结论，识别历史落库回看）+ **语音识别 ASR**（qwen3-asr-flash）+ **语音合成 TTS**（qwen3-tts-flash），模型恒定百炼 |
| 系统管理 admin    | 配置写 .env 热生效（免重启）、敏感信息脱敏、连接测试、百炼免费额度模型目录（5 大类一键切换）、系统日志（环形缓冲 200 条）、用户管理                                               |

**降级设计**：所有 LLM 依赖点均具备"无 Key 自动降级"能力（关键词解析 / 模板报告），拔掉 API Key 系统依然完整可用。v1.0.1 新增统一调用底座（`app/core/llm_invoker.py`）：限流/超时类异常**指数退避重试（1s/2s/4s）→ 熔断（连续失败 3 次冷却 60s）→ Provider 链（aliyun/amd/ollama）自动降级 → 规则兜底**，每次调用返回 provider/model/tokens/degraded 审计信息。

---

## 2. 技术栈

| 类别                 | 技术                                    | 版本           | 用途                                             |
| -------------------- | --------------------------------------- | -------------- | ------------------------------------------------ |
| Web 框架             | FastAPI                                 | 0.115.0        | REST API + Swagger 文档（/docs）                 |
| ASGI 服务器          | Uvicorn                                 | 0.30.0         | 高性能异步服务                                   |
| ORM                  | SQLAlchemy                              | 2.0.35         | 13 张表数据模型                                  |
| 空间 ORM             | GeoAlchemy2                             | 0.15.1         | POINT / MULTIPOLYGON 几何字段                    |
| 数据库               | PostgreSQL + PostGIS                    | 14+ / 3.5      | 空间数据存储与索引                               |
| 数据校验             | Pydantic + pydantic-settings            | 2.9.0          | 请求/响应模型 + .env 配置类                      |
| **Agent 编排** | **LangGraph（StateGraph）**       | 0.2.64         | 8 节点状态图：并行 fan-out/join + 评审循环 + HITL 审批 |
| **LLM 框架**   | **LangChain + langchain-openai**  | 0.3.17         | ChatOpenAI / OpenAIEmbeddings                    |
| **LLM 可靠性** | **统一调用层 llm_invoker**              | —              | 重试(1s/2s/4s)→熔断(3次/60s)→Provider 链降级     |
| **状态持久化** | **langgraph-checkpoint-postgres + psycopg[binary]** | 2.0.15 / 3.3.6 | PostgresSaver 检查点（不可用降级 MemorySaver）   |
| **Rerank 精排** | **DashScope qwen3-rerank**              | —              | 混合检索精排，失败降级 RRF 融合原序              |
| **工具协议** | **MCP（mcp + langchain-mcp-adapters）** | 2.2.0 / 0.2.0  | 高德天气只读数据源（FastMCP stdio）              |
| **可观测** | **Langfuse（私有化，可选）**            | 4.15.6         | LangGraph callbacks 全链路 trace                 |
| 文本切分             | langchain-text-splitters                | 0.3.5          | RecursiveCharacterTextSplitter（中文分隔符优先） |
| PDF 解析             | pdfplumber / pypdf / PyMuPDF / RapidOCR | —             | 四层兜底文本提取（含 OCR 扫描版）                |
| 向量库               | pgvector                                | 0.3.6          | 预留向量列升级                                   |
| 认证                 | bcrypt + python-jose                    | 4.2.1 / 3.3.0  | 密码哈希 + JWT HS256                             |
| 空间计算             | geopandas / shapely                     | 1.0.1 / 2.0.5  | 网格聚类、缓冲区分析                             |
| 数据处理             | pandas / numpy                          | 2.2.2 / 1.26.4 | 数据导入与聚合                                   |
| HTTP / 上传          | httpx / aiofiles / python-multipart     | —             | 异步请求 / 文件上传                              |

**大模型服务（三提供商动态切换 + 恒定百炼多模态）**：

| 提供商             | 模型类型  | 模型                                   | 说明                                    |
| ------------------ | --------- | -------------------------------------- | --------------------------------------- |
| 阿里百炼 DashScope | Chat      | qwen-plus                              | 主力提供商，OpenAI 兼容模式             |
| AMD GPU Cloud      | Chat      | DeepSeek-V4-Flash / Qwen3.8-Flash-Next | 备选提供商（Qwen3.8 需时间窗口校验）    |
| 本地 Ollama        | Chat      | qwen2.5:7b                             | 离线免费运行                            |
| 阿里百炼（恒定）   | Embedding | text-embedding-v3                      | 与 Chat 提供商解耦，不受切换影响        |
| 阿里百炼（恒定）   | 视觉      | qwen-vl-plus                           | 火情图像识别，base64 多模态消息         |
| 阿里百炼（恒定）   | 语音 ASR  | qwen3-asr-flash                        | chat/completions + input_audio data URI |
| 阿里百炼（恒定）   | 语音 TTS  | qwen3-tts-flash                        | 原生 multimodal 端点，文本转 wav        |

> **Embedding / 视觉 / 语音模型恒定使用阿里百炼**，与 `ACTIVE_LLM_PROVIDER` 切换完全解耦。

---

## 3. 项目结构

```
fire_agent_back/
├── app/
│   ├── main.py                  ← 入口：lifespan 建表 + 幂等补列 + 种子管理员 + CORS + 路由注册
│   ├── core/
│   │   ├── config.py            ← 全局配置（pydantic-settings 读 .env）
│   │   ├── database.py          ← SQLAlchemy 引擎 / SessionLocal / Base
│   │   ├── security.py          ← bcrypt 哈希 + JWT 编解码 + get_current_user/admin
│   │   ├── llm.py               ← 多提供商 LLM 路由（aliyun/amd/ollama）+ Embedding
│   │   │                          + 视觉/ASR/TTS 客户端 + list_provider_models
│   │   ├── llm_invoker.py       ← 统一 LLM 调用层：重试/熔断/Provider 链降级/结构化输出/流式/token 审计
│   │   ├── checkpointer.py      ← LangGraph PostgresSaver 检查点（降级 MemorySaver）
│   │   ├── reranker.py          ← DashScope qwen3-rerank 精排（降级 RRF）
│   │   ├── mcp_client.py        ← MCP 客户端（高德天气工具，静默降级）
│   │   ├── memory_store.py      ← 用户偏好长期记忆（PostgresStore JSONB）
│   │   ├── observability.py     ← Langfuse 观测 callbacks（未启用降级纯日志）
│   │   └── report_channels.py   ← 报告流式增量通道（SSE report_delta）
│   ├── models/                  ← 13 张 ORM 表
│   │   ├── user.py / fire_point.py / fire_risk.py / region_boundary.py
│   │   ├── emergency_resource.py / task.py / report.py
│   │   ├── kb_document.py / query_history.py / rag_history.py / vision.py
│   ├── schemas/                 ← Pydantic 请求/响应模型（auth/query/rag/agent/report/admin/dashboard）
│   ├── repositories/            ← fire_repository（火点/预测/边界）/ report_repository
│   ├── services/
│   │   ├── query_service.py     ← 双引擎意图识别 + 三种意图执行器 + GeoJSON 生成
│   │   ├── rag_service.py       ← 上传/四层提取/切分/向量化/混合检索/问答
│   │   └── data_service.py
│   ├── agents/
│   │   ├── orchestrator_agent.py ← LangGraph StateGraph（8 节点：并行 fan-out/join + 评审循环 + HITL 审批）
│   │   ├── data_agent.py        ← 火点查询与聚合统计
│   │   ├── gis_agent.py         ← 0.1° 网格聚类热点 + 缓冲区分析
│   │   ├── rag_agent.py         ← 知识库检索节点
│   │   └── report_agent.py      ← LLM 五段式 Markdown 报告（模板兜底）
│   ├── workflows/               ← agent_workflow（LangGraph 封装）
│   ├── utils/                   ← risk_level（等级分档）/ geojson
│   └── api/v1/routes/           ← 8 个路由模块
│       ├── auth.py / dashboard.py / query.py / rag.py
│       ├── agent.py / report.py / admin.py / media.py(视觉与语音)
├── scripts/                     ← 数据导入与评估脚本
│   ├── init_db.py               ← 启用 PostGIS + 建表
│   ├── import_fire_points.py    ← Yunnan_fire.json → historical_fire_points（5411 条）
│   ├── import_predict_risks.py  ← 逐日/逐月预测 JSON → predicted_fire_risks
│   ├── import_region_boundaries.py ← Yunnan_border.json → region_boundaries（16 州市）
│   ├── run_all_imports.py       ← 一键全量导入（支持自定义路径 + 耗时统计）
│   ├── eval_regression.py       ← 回归评估（golden set 四类确定性指标，离线/live）
│   └── golden_set.json          ← 评估回归金标用例（10 用例）
├── mcp_server/
│   └── weather_server.py        ← MCP 天气数据源（FastMCP stdio：高德 geo→adcode→weather）
├── Dockerfile                   ← 后端镜像（python:3.12-slim + 健康检查）
├── docker-compose.yml           ← 全栈编排（db/backend/frontend + Langfuse 可选 profile）
├── .env.example                 ← 环境变量模板
├── sql/public.sql               ← 数据库全量导出（建表语句 + 数据）
├── data/knowledge_base/         ← 知识库上传文档落盘目录（自动创建）
├── data/vision_uploads/         ← 火情识别图片落盘目录（uuid 命名）
├── .env                         ← 运行时配置
├── 整体实现.md                   ← 毕业论文风格完整实现文档（架构图/ER图/流程图）
└── requirements.txt
```

---

## 4. 核心功能详解

### 4.1 应用入口（main.py）

- `lifespan` 启动钩子：`create_all` 自动建表 → 幂等补列（兼容旧库）→ 种子管理员（admin/123456）
- CORS 中间件放行前端 5173/4173
- 8 个路由模块挂载 `/api/v1/*`，Swagger 文档：`http://localhost:8000/docs`

### 4.2 智能查询（query.py + QueryService）

- **双引擎意图识别**：LLM（qwen-plus，temperature=0.05，Prompt 内置 16 州市清单/季节映射/置信度枚举，输出 JSON）+ 关键词正则降级（州市简称映射"普洱"→"普洱市"、"版纳"→"西双版纳傣族自治州"；"春季"→[3,4,5]月）
- **三种意图执行器**：历史火点（日期区间+FRP 排序）/ 预测火险（risk_score 排序+风险分档配色 GeoJSON）/ 数据汇总（Top 城市统计）
- **历史落库去重**：按 user + query_text 去重，重复查询仅更新时间与摘要

### 4.3 RAG 知识库（rag.py + RagService）

- **四层 PDF 文本提取**：pdfplumber → pypdf → PyMuPDF 文本层 → RapidOCR 图像识别（解决扫描版/自定义字体乱码，如 GB/T 36743-2018）
- **切分**：RecursiveCharacterTextSplitter（chunk_size=500，overlap=50，中文分隔符 `\n\n → \n → 。 → ，` 优先）
- **向量化**：OpenAIEmbeddings（text-embedding-v3，阿里百炼）
- **混合检索**：中文分词 + 向量余弦 + 关键词加权（2 字词优先）→ **Rerank 精排**（qwen3-rerank，失败/未启用降级 RRF 融合原序），Top-K 分片；复杂查询自适应改写（最多 3 轮检索环）
- **问答**：LLM 必须引用来源编号；未检索到匹配文档时明确声明；`POST /ask/stream` SSE 流式（meta→delta→done，半截不落库）

### 4.4 多 Agent 协作（agent.py + OrchestratorAgent）

LangGraph StateGraph 状态机（v1.0.1 拓扑）：

```
parse_task → (query_data → analyze_gis) ∥ retrieve_knowledge → join
           → generate_report → review_report →(≤2轮循环)→ approval_gate(HITL) → END
(Orchestrator)  (DataAgent)   (GisAgent)   (RagAgent)  (ReportAgent)  (Reviewer)   (interrupt/resume)
```

- **计划驱动路由**：`parse_task` 结构化产出 TaskPlan；query_data / analyze_gis / generate_report 为固定步骤（防"跑完无报告"），LLM 仅决定是否追加知识库检索
- **并行 fan-out/join**：query_data ∥ retrieve_knowledge 并行执行，`operator.add` reducer 只写增量，join 屏障汇聚
- **反思重试**：查询为空时 LLM 反思放宽参数重查（≤2 轮）
- **评审循环 + 硬护栏**：低温度 LLM 评审 + 不依赖 LLM 的硬护栏一票否决（≥800 字/必备章节/真实数据引用），驳回带意见重写（≤2 轮）
- **HITL 审批**：`approval_gate` interrupt 暂停（状态 awaiting_approval），`POST /tasks/{id}/resume` 注入 approve / edit / reject 后以同 thread_id 续跑（PostgresSaver 持久化中断态）
- **异步任务 + SSE**：`POST /tasks` 立即返回 task_id 后台执行；节点步骤增量落库（running 预写 + 终态覆盖），`GET /tasks/{id}/stream?token=` SSE 推送节点级进度/报告增量/终态（断线重放，单连接上限 1800s）
- **报告七章刚性模板**：一、执行摘要 / 二、数据来源与分析方法 / 三、火情数据分析 / 四、高风险区域识别 / 五、重点巡防建议 / 六、结论与展望 / 附：参考依据（标题顺序不可改、≥800 字、真实数据引用、自动追加开发者署名）；报告按查询语义自动归类 daily/weekly/monthly/special 落库，支持报告中心类型筛选
- 任务与步骤（含 JSON payload）落库 `agent_tasks` / `agent_task_steps`，报告落库 `analysis_reports`（含 llm_provider / llm_model / llm_tokens 审计）；报告软删（用户自删 hidden / 管理员删 deleted），任务详情 include_deleted 支持历史回放

### 4.5 系统管理（admin.py）

- **配置热生效**：`setattr(settings, ...)` 内存生效 + `dotenv.set_key` 写回 .env，**无需重启**
- **脱敏**：API Key `sk-***xxx`（前 3 后 3），数据库 URL 只显示 `@` 之后部分
- **连接测试**：`/test/db`（SELECT 1）、`/test/llm`（真实 invoke）
- **百炼免费额度模型目录**：`GET /llm/models` 调用提供商 `/models` 端点实时校验可用性，与内置免费额度目录（大语言/视觉/全模态/语音/向量 5 大类，35 个免费模型）交叉比对，按"免费优先→有效期长→当前使用→已验证"排序，附密钥概况（脱敏）与控制台直达链接；全类型模型支持一键「使用」切换（写 .env 热生效）
- **系统日志**：`log_system_event()` 环形缓冲 200 条
- **用户管理**：仅管理员；角色修改防自改、删除用户防自删

### 4.6 视觉与语音模块（media.py · /api/v1/vision）

**AI 火情图像识别**：

- `POST /analyze`：上传 jpg/png/webp/bmp（≤10MB）→ base64 多模态消息（内置森林火灾监测专家提示词）→ 视觉模型输出**四段结构化 Markdown**（火情判定：明火/烟雾/无异常 / 场景描述 / 严重程度：轻微-危急四级 / 处置建议）；非火情图片明确标注
- 图片 uuid 命名落盘 `data/vision_uploads/`，识别结果落库 `vision_history`（用户隔离）
- 历史列表/详情/删除/图片鉴权流（`GET /image/{id}`）全链路用户数据隔离

**语音识别（ASR）与语音合成（TTS）**：

| 能力     | 端点                           | 实现                                                                                                                                           |
| -------- | ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| 语音识别 | `POST /audio/transcriptions` | 百炼`chat/completions` + `input_audio` **data URI** 格式（裸 base64 会报"URL 无效"）；wav/mp3/opus/aac/amr，≤20MB                   |
| 语音合成 | `POST /audio/speech`         | 百炼**原生** multimodal-generation 端点（兼容模式无 /audio/speech），必传 `voice`（Cherry），响应音频 URL 下载为 wav 流；文本限 500 字 |

> ASR / TTS 恒定百炼（ASR_MODEL / TTS_MODEL），不受 ACTIVE_LLM_PROVIDER 切换影响；视觉模型按 VISION_PROVIDER 路由（aliyun 百炼 / amd GPU Cloud）；未配置 Key 时返回友好提示不抛异常。

### 4.7 LLM 多提供商路由（core/llm.py）

```
get_llm() ─── ACTIVE_LLM_PROVIDER（.env / 系统管理页在线切换）
   ├─ aliyun → ChatOpenAI(百炼兼容端点, qwen-plus)
   ├─ amd    → ChatOpenAI(AMD端点, DeepSeek-V4-Flash)
   └─ ollama → ChatOpenAI(localhost:11434/v1, qwen2.5:7b)

get_embedding() ─── 恒定阿里百炼 text-embedding-v3
```

> **v1.0.1**：业务代码统一经 `app/core/llm_invoker.py`（`invoke_llm` / `invoke_structured` / `stream_llm`）调用，
> 内置指数退避重试 → 熔断（3 次/60s）→ Provider 链降级 → 规则兜底，并携带 provider/model/tokens/degraded 审计；
> `get_llm` 仅为底层构建函数，新代码禁止直接调用。

---

## 5. 数据库设计

数据库共 **13 张业务表**（另含 PostGIS 系统表），完整建表语句见 `sql/public.sql`：

| 分类     | 表名                       | 说明                                                              | 数据规模          |
| -------- | -------------------------- | ----------------------------------------------------------------- | ----------------- |
| 业务数据 | `historical_fire_points` | 历史火点（含 geom POINT 4326、frp、置信度，日期/城市/置信度索引） | **5411 条** |
| 业务数据 | `predicted_fire_risks`   | 预测火险（daily/monthly 双视图，fire_level 1-5，risk_score）      | 2025—2026 全量   |
| 业务数据 | `region_boundaries`      | 16 州市边界（MULTIPOLYGON 4326）                                  | 16 条             |
| 业务数据 | `emergency_resources`    | 应急资源（预留）                                                  | 待导入            |
| 平台数据 | `users`                  | 用户（bcrypt 哈希，role user/admin）                              | 按注册增长        |
| 平台数据 | `query_history`          | 查询历史（按用户+文本去重）                                       | 按使用增长        |
| 平台数据 | `rag_history`            | RAG 问答历史                                                      | 按使用增长        |
| 平台数据 | `agent_tasks`            | Agent 任务（status/report_id 外键）                               | 按使用增长        |
| 平台数据 | `agent_task_steps`       | 任务步骤（JSON payload，一对多级联删除）                          | 按使用增长        |
| 平台数据 | `analysis_reports`       | 分析报告（Markdown 正文）                                         | 按使用增长        |
| 平台数据 | `kb_documents`           | 知识库文档（状态机 pending→processing→ready/failed）            | 按上传增长        |
| 平台数据 | `kb_chunks`              | 知识库分片（content/token_count/embedding）                       | 按上传增长        |
| 平台数据 | `vision_history`         | AI 火情识别历史（图片路径 + Markdown 识别结果 + 模型名）          | 按识别增长        |

**关系**：`agent_tasks 1—N agent_task_steps`、`agent_tasks N—1 analysis_reports`、`kb_documents 1—N kb_chunks`、`users 1—N query_history/rag_history/agent_tasks/analysis_reports/kb_documents/vision_history`。

E-R 图与完整表结构说明见《[整体实现.md](./整体实现.md)》第 5 章。

---

## 6. API 接口总表

统一响应格式：`{ code, message, data }`。

### 认证 `/api/v1/auth`

| 方法 | 路径          | 鉴权   | 说明                                    |
| ---- | ------------- | ------ | --------------------------------------- |
| POST | `/register` | -      | 注册（查重 + bcrypt + JWT，注册即登录） |
| POST | `/login`    | -      | 登录（JWT 24h）                         |
| GET  | `/me`       | Bearer | 当前用户信息                            |

### 大屏 `/api/v1/dashboard`

| 方法 | 路径               | 说明                                         |
| ---- | ------------------ | -------------------------------------------- |
| GET  | `/history-fires` | 历史火点（日期/城市/置信度/分页，上限 5000） |
| GET  | `/predict-risks` | 预测火险（年/月/日/daily\|monthly/城市）     |
| GET  | `/summary`       | 摘要统计（总数/高置信/平均 FRP/Top5 城市）   |

### 智能查询 `/api/v1/query`

| 方法   | 路径              | 鉴权   | 说明                              |
| ------ | ----------------- | ------ | --------------------------------- |
| POST   | `/parse`        | -      | 仅解析意图（LLM/关键词）          |
| POST   | `/execute`      | -      | 解析 + 执行 + 四维结果 + 历史落库 |
| GET    | `/history`      | Bearer | 当前用户查询历史（用户隔离）      |
| DELETE | `/history/{id}` | Bearer | 删除单条历史                      |

### 知识库 `/api/v1/rag`

| 方法   | 路径                | 说明                                 |
| ------ | ------------------- | ------------------------------------ |
| POST   | `/ask`            | RAG 问答（回答 + 引用 + llm_used）   |
| POST   | `/ask/stream`     | **RAG 流式问答**（SSE：meta→delta→done） |
| GET    | `/history`        | 问答历史（用户隔离）                 |
| DELETE | `/history/{id}`   | 删除问答历史                         |
| POST   | `/documents`      | 上传文档（multipart，category 表单） |
| GET    | `/documents`      | 文档列表（用户隔离）                 |
| DELETE | `/documents/{id}` | 删除文档（文件 + 分片级联）          |

### Agent `/api/v1/agent`

| 方法   | 路径                                  | 说明                                          |
| ------ | ------------------------------------- | --------------------------------------------- |
| POST   | `/tasks`                            | 创建任务（**立即返回 task_id，后台异步执行**） |
| GET    | `/tasks`                            | 任务列表（附报告生成 provider/详细模型名）    |
| GET    | `/tasks/{task_id}`                  | 任务详情（执行步骤 + 报告，历史回放）         |
| GET    | `/tasks/{task_id}/stream?token=`    | **SSE 实时进度**（节点步骤/报告增量/审批/终态，断线重放） |
| POST   | `/tasks/{task_id}/resume`           | **HITL 审批恢复**（approve / edit / reject）  |
| DELETE | `/tasks/{task_id}`                  | 删除任务（级联步骤）                          |
| GET    | `/capabilities`                     | 「系统能力」面板（编排/熔断/检查点/MCP/观测真实运行态） |
| GET    | `/status`                           | 5 个 Agent 运行状态                           |

### 报告 `/api/v1/reports`

| 方法   | 路径                            | 说明                                         |
| ------ | ------------------------------- | -------------------------------------------- |
| GET    | `/list`                       | 列表（page/page_size/report_type，用户隔离） |
| GET    | `/{id}`                       | 详情（Markdown 正文）                        |
| POST   | `/generate`                   | 生成/保存报告                                |
| DELETE | `/{id}`                       | 删除报告                                     |
| GET    | `/export/{id}?format=md\|html` | 导出（md 附件 / HTML 打印模板）              |

### 系统管理 `/api/v1/admin`

| 方法   | 路径                      | 鉴权             | 说明                                                      |
| ------ | ------------------------- | ---------------- | --------------------------------------------------------- |
| GET    | `/status`               | 登录             | 运行状态总览                                              |
| GET    | `/config`               | 登录             | 当前配置（**脱敏**）                                |
| POST   | `/config`               | 登录             | 更新配置（**写 .env 热生效**）                      |
| POST   | `/test/db`              | 登录             | 数据库连接测试                                            |
| POST   | `/test/llm`             | 登录             | LLM 连接测试（真实 invoke）                               |
| GET    | `/logs?limit=`          | 登录             | 系统日志（环形缓冲 200）                                  |
| GET    | `/llm/models?provider=` | 登录             | 提供商可用模型列表 + 百炼免费额度目录（5 大类）+ 密钥概况 |
| GET    | `/users`                | **管理员** | 用户列表                                                  |
| PUT    | `/users/{id}/role`      | **管理员** | 修改角色（防自改）                                        |
| DELETE | `/users/{id}`           | **管理员** | 删除用户（防自删）                                        |

### 视觉与语音 `/api/v1/vision`

| 方法   | 路径                      | 鉴权   | 说明                                                              |
| ------ | ------------------------- | ------ | ----------------------------------------------------------------- |
| POST   | `/analyze`              | Bearer | **火情图像识别**（qwen-vl 多模态，结果落库 vision_history） |
| GET    | `/history`              | Bearer | 识别历史列表（用户隔离，上限 100）                                |
| GET    | `/history/{id}`         | Bearer | 识别历史详情                                                      |
| DELETE | `/history/{id}`         | Bearer | 删除识别记录（连同本地图片）                                      |
| GET    | `/image/{id}`           | Bearer | 识别图片鉴权流（FileResponse）                                    |
| POST   | `/audio/transcriptions` | Bearer | **语音识别 ASR**（wav → 文本，qwen3-asr-flash）            |
| POST   | `/audio/speech`         | Bearer | **语音合成 TTS**（文本 → wav 音频流，qwen3-tts-flash）     |

### 其他

| 方法 | 路径        | 说明               |
| ---- | ----------- | ------------------ |
| GET  | `/`       | 服务信息           |
| GET  | `/health` | 健康检查           |
| GET  | `/docs`   | Swagger 交互式文档 |

---

## 7. 环境要求

| 组件       | 要求                                               |
| ---------- | -------------------------------------------------- |
| 操作系统   | Windows / Linux / macOS                            |
| Python     | **3.10+**（推荐 conda 独立环境）             |
| PostgreSQL | 14+ 并启用**PostGIS** 扩展                   |
| 网络       | 需访问阿里百炼 / AMD 端点（离线可切换本地 Ollama） |
| 容器化（可选） | Docker + Docker Compose（一键拉起 db/backend/frontend，可选 Langfuse 观测 profile） |

---

## 8. 快速启动

### 8.0 Docker Compose 一键部署（v1.0.1 新增，推荐）

```bash
cp .env.example .env          # 准备环境变量（填入真实 Key）
docker compose up -d          # 拉起 postgis/db + backend + frontend 全栈
docker compose --profile observability up -d   # 可选：加起 Langfuse 私有化观测
```

- 后端 `Dockerfile`：python:3.12-slim + 依赖层缓存 + `/health` 健康检查；
- 前端镜像内置 nginx 配置：`/api` 反代 **关闭缓冲（proxy_buffering off）+ 1800s 超时**，保证 SSE 实时进度/报告增量/RAG 流式不被缓冲；
- db 健康检查就绪后自动启动 backend（容器内 DATABASE_URL 覆盖为 `db` 主机名），数据卷持久化；
- 启动后访问前端 `http://localhost:8080`、后端 Swagger `http://localhost:8000/docs`。

### 8.1 准备数据库（一次性）

1. 安装 PostgreSQL 14+，启用 PostGIS 扩展；
2. 创建空数据库 `fire_agent`：

```sql
CREATE DATABASE fire_agent;
-- 使用 fire_agent 库后执行：
CREATE EXTENSION IF NOT EXISTS postgis;
```

### 8.2 安装依赖并配置

```bash
# 1. 创建并激活 Python 环境
conda create -n fire_agent_back python=3.10
conda activate fire_agent_back

# 2. 进入项目目录并安装依赖
cd fire_agent_back
pip install -r requirements.txt

# 3. 在项目根目录创建 .env（配置见第 10 节）
```

### 8.3 导入数据并启动

```bash
# 4. 一键导入数据（建表 → 边界 → 火点 → 预测）
python scripts/run_all_imports.py

# 5. 启动服务
uvicorn app.main:app --reload --port 8000
```

启动成功后：

- 服务地址：`http://localhost:8000`
- Swagger 文档：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/health`
- **默认管理员**：`admin / 123456`（首次启动自动创建，已存在则跳过）

### 8.4 启动前端（配套）

```bash
cd fire_agent_front
npm install
npm run dev          # http://localhost:5173
```

---

## 9. 数据导入

### 数据来源

| 数据     | 来源                       | 规模                                             |
| -------- | -------------------------- | ------------------------------------------------ |
| 历史火点 | NASA FIRMS MODIS（云南省） | **5411 条**（含 FRP/置信度/昼夜/亮度温度） |
| 预测火险 | GTWR 模型预测              | 2025—2026 逐日 + 逐月，含 fire_level 1-5        |
| 行政边界 | 云南省 16 州市 GeoJSON     | 16 个 MULTIPOLYGON                               |

### 导入脚本

| 脚本                                    | 功能                                                                                            |
| --------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `scripts/init_db.py`                  | 启用 PostGIS 扩展 + 建全部表                                                                    |
| `scripts/import_fire_points.py`       | Yunnan_fire.json → historical_fire_points（含 geom 构建）                                      |
| `scripts/import_predict_risks.py`     | 逐日/逐月 JSON → predicted_fire_risks                                                          |
| `scripts/import_region_boundaries.py` | Yunnan_border.json → region_boundaries（SRID=4326）                                            |
| `scripts/run_all_imports.py`          | **一键全量导入**（建表→边界→火点→预测，支持 `--fire-path` 等自定义路径，带耗时统计） |

```bash
# 一键全量导入
python scripts/run_all_imports.py
```

> 也可以直接使用 `sql/public.sql`（全量建表 + 数据导出）通过 Navicat / psql 恢复数据库。

---

## 10. 配置说明（.env）

在项目根目录创建 `.env` 文件：

```env
# 数据库（需已启用 PostGIS）
DATABASE_URL=postgresql://postgres:密码@localhost:5432/fire_agent

# JWT 签名密钥（生产环境务必修改）
JWT_SECRET=自定义强密钥

# 高德地图（天气 API）
AMAP_KEY=你的key

# 活跃 LLM 提供商 aliyun | amd | ollama
ACTIVE_LLM_PROVIDER=aliyun

# 阿里百炼（Chat + Embedding，OpenAI 兼容模式）
LLM_API_KEY=sk-xxxxxxxx
LLM_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-plus
EMBEDDING_MODEL=text-embedding-v3

# 视觉 / 语音模型（恒定百炼，不受 ACTIVE_LLM_PROVIDER 影响）
VISION_MODEL=qwen-vl-plus
ASR_MODEL=qwen3-asr-flash
TTS_MODEL=qwen3-tts-flash

# AMD GPU Cloud（备选 Chat 提供商）
AMD_API_KEY=你的key
AMD_API_BASE=https://developer.amd.com.cn/radeon/v1
AMD_MODEL=DeepSeek-V4-Flash

# Qwen3.8-Flash-Next 可用时间窗口（YYYY-MM-DD HH:MM:SS，空表示不限）
QWEN3_8_FLASH_START=
QWEN3_8_FLASH_END=

# 本地 Ollama（离线备选）
OLLAMA_API_BASE=http://localhost:11434/v1
OLLAMA_MODEL=qwen2.5:7b

# RAG 知识库
KB_UPLOAD_DIR=data/knowledge_base
KB_CHUNK_SIZE=500
KB_CHUNK_OVERLAP=50
KB_TOP_K=5

# Rerank 精排（DashScope qwen3-rerank，使用 LLM_API_KEY；失败自动降级 RRF 融合）
RERANK_ENABLED=true
RERANK_MODEL=qwen3-rerank

# Agent 参数：报告生成后需人工审批（HITL）才定稿
AGENT_REQUIRE_APPROVAL=true

# P2 功能开关
LLM_STREAM_ENABLED=true      # 全链路流式（报告/RAG 回答逐字推送）
PREFERENCES_ENABLED=true     # 用户偏好长期记忆（PostgresStore）
MCP_ENABLED=true             # MCP 高德天气只读数据源（失败静默跳过）

# Langfuse 私有化观测（未启用或未配密钥时降级纯日志）
LANGFUSE_ENABLED=false
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=

# 视觉提供商（视觉可切 aliyun/amd；语音恒定百炼）
VISION_PROVIDER=aliyun
```

**配置要点**：

- **所有 LLM 参数均非必填**：LLM_API_KEY 为空时系统自动降级（关键词解析/模板报告），大屏、地图、图表、报告管理等非 AI 功能完全可用；
- 模型配置也可不写 .env，直接在前端「系统管理 → 模型接入」页在线填写，**保存即写入 .env 并热生效（无需重启）**，回显自动脱敏；也可通过百炼免费额度模型目录一键切换全类型模型（Chat/视觉/ASR/TTS/Embedding）；
- AMD 模型名必须与 AMD `/models` 端点返回的可用模型名精确匹配（如 `DeepSeek-V4-Flash`），否则 404；
- **Embedding / 语音模型恒定使用阿里百炼**（LLM_API_KEY），与 ACTIVE_LLM_PROVIDER 无关；视觉模型默认百炼、可通过 VISION_PROVIDER 切换 amd；
- **ASR/TTS 需配置 LLM_API_KEY（百炼）**：语音识别走 `chat/completions + input_audio`，语音合成走百炼原生 multimodal 端点，与其他提供商的兼容端点不通用；
- **P2 开关均可安全关闭**：RERANK_ENABLED / LLM_STREAM_ENABLED / PREFERENCES_ENABLED / MCP_ENABLED / LANGFUSE_ENABLED 关闭或依赖缺失时自动降级，不影响核心功能；Langfuse 可配合 `docker compose --profile observability` 私有化部署。

---

## 11. 常见问题

| 问题                              | 解决方案                                                                                                                                |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| 启动报数据库连接失败              | 检查 PostgreSQL 是否运行、`.env` 中 DATABASE_URL 密码是否正确、`fire_agent` 库是否已创建                                            |
| `CREATE EXTENSION postgis` 报错 | 先安装 PostGIS 扩展包（Windows 安装程序勾选 / Linux:`apt install postgresql-14-postgis-3`）                                           |
| AMD 模型连接 404                  | 模型名与 AMD`/models` 端点不匹配；改为可用模型名 `DeepSeek-V4-Flash`                                                                |
| PDF 提取乱码                      | 自定义字体编码 PDF 会走 OCR 兜底（PyMuPDF 渲染 + RapidOCR）；确认已安装`rapidocr-onnxruntime`                                         |
| OCR 依赖安装失败                  | `pip install rapidocr-onnxruntime`（首次运行会下载 onnx 模型，需网络）                                                                |
| 智能查询走关键词而非 LLM          | LLM_API_KEY 未配置或 LLM 调用异常自动降级；在「系统管理 → 模型接入」配置并测试连接                                                     |
| 语音识别报"URL 无效"              | ASR 音频必须以 data URI（`data:audio/wav;base64,...`）嵌入 input_audio，裸 base64 不被百炼接受；前端 speech.js 已按此编码 WAV         |
| 语音合成 404 / 不支持             | 百炼 OpenAI 兼容模式无 /audio/speech 端点，系统已改走原生 multimodal-generation 端点；确认 TTS_MODEL 为 qwen3-tts-flash 或 cosyvoice-v2 |
| 火情识别返回"未配置 API Key"      | 视觉模型默认使用百炼 LLM_API_KEY（VISION_PROVIDER 切到 amd 后改用 AMD_API_KEY）；在「系统管理 → 模型接入」配置对应 Key 后重试（VISION_MODEL 默认 qwen-vl-plus） |
| 前端跨域报错                      | 开发环境由 Vite 代理解决；生产环境需在 Nginx 配置`/api` 反向代理，或修改 CORS_ORIGINS                                                 |
| 修改 .env 不生效                  | 直接改文件需重启；推荐用「系统管理 → 模型接入」保存（写 .env + 内存双写，免重启）                                                      |
| SSE 进度不推送 / 提前断开         | 反向代理需对 `/api` 关闭缓冲（`proxy_buffering off`）并放宽读超时（参考前端仓库 nginx.conf 的 1800s 配置）；EventSource 以 `?token=` 传 JWT |
| MCP 天气未生效                    | 确认 MCP_ENABLED=true 且已安装 `mcp` / `langchain-mcp-adapters`；未配 AMAP_KEY 或调用失败时静默跳过，不阻断报告生成                     |

---

*开发者：wjl（19136220923@163.com） · 后端源码：https://gitee.com/wjl2004/fire_agent_back · 前端源码：https://gitee.com/wjl2004/fire_agent_front*
