# FlameSentry · Smart Forest-Fire Early-Warning & Multi-Agent Collaboration Platform — Backend (fire_agent_back)

> **Current version: v1.0.1** (P0 reliability foundation + P1 orchestration upgrade + P2 engineering modules; see Chapter 13 changelog in the [Implementation doc](./整体实现.md), Chinese)
> This is the backend of the "FlameSentry · Smart Forest-Fire Early-Warning & Multi-Agent Collaboration Platform" (practical display name: **焰哨多Agent与可视化平台**), built on **FastAPI + PostgreSQL/PostGIS + LangChain + LangGraph**.
> Companion frontend: [fire_agent_front](https://gitee.com/wjl2004/fire_agent_front) (Vue3 + OpenLayers + ECharts)
> The complete system design document is in this repo: [Implementation.md](./整体实现.md) (Chinese).
> **Online demo**: https://wjl2004.ffuf.cn/
> **GitHub repo**: https://github.com/wjl-cong/fire_agent (⭐ Star welcome!)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Tech Stack](#2-tech-stack)
3. [Project Structure](#3-project-structure)
4. [Core Features in Detail](#4-core-features-in-detail)
5. [Database Design](#5-database-design)
6. [API Reference](#6-api-reference)
7. [Environment Requirements](#7-environment-requirements)
8. [Quick Start](#8-quick-start)
9. [Data Import](#9-data-import)
10. [Configuration (.env)](#10-configuration-env)
11. [FAQ](#11-faq)

---

## 1. Project Overview

The backend is an API service for a front-end/back-end separated architecture, providing the following core capabilities:

| Module | Core Capabilities |
|---|---|
| Auth | JWT (HS256, 24h) register/login, bcrypt password hashing, admin/user dual roles, user data isolation |
| Dashboard | Historical fire points (5,411 NASA FIRMS records) / predicted fire risk (GTWR model) / summary statistics (Top 5 cities) |
| Smart Query | Natural language → LLM·keyword dual-engine intent recognition → structured query → summary/table/chart/GeoJSON four-dimensional results, history persisted with dedup |
| Knowledge Base (RAG) | PDF/TXT/MD upload → four-layer text extraction (incl. OCR for scanned pages) → Chinese-aware chunking → vectorization → hybrid retrieval + **Rerank (qwen3-rerank, RRF fallback)** → LLM answer with cited sources; **/ask/stream SSE streaming** and adaptive query rewriting for complex queries |
| Agent Collaboration | LangGraph StateGraph 8-node orchestration (**parallel fan-out/join + review loop + HITL approval**), async task execution with **SSE node-level live progress**, tasks/steps/reports persisted (history replay), rigid seven-section report template |
| Reports | Report CRUD + export as Markdown / HTML (print template) |
| Vision & Speech | **AI fire image recognition** (qwen-vl multimodal, four-part structured conclusion, recognition history persisted for review) + **Speech Recognition (ASR)** (qwen3-asr-flash) + **Speech Synthesis (TTS)** (qwen3-tts-flash), models fixed to Bailian |
| System Admin | Config written to .env with hot reload (no restart), sensitive info masking, connection tests, Bailian free-quota model catalog (5 categories, one-click switch), system logs (ring buffer of 200 entries), user management |

**Degradation design**: Every LLM-dependent point has "no-key auto-degradation" capability (keyword parsing / template reports). The system stays fully usable even without any API key. v1.0.1 adds a unified invocation layer (`app/core/llm_invoker.py`): **exponential-backoff retry (1s/2s/4s) for rate-limit/timeout/connection errors → circuit breaker (3 consecutive failures, 60s cooldown) → provider-chain (aliyun/amd/ollama) auto-failover → rule-based fallback**, with provider/model/tokens/degraded audit metadata on every call.

---

## 2. Tech Stack

| Category | Technology | Version | Purpose |
|---|---|---|---|
| Web framework | FastAPI | 0.115.0 | REST API + Swagger docs (/docs) |
| ASGI server | Uvicorn | 0.30.0 | High-performance async server |
| ORM | SQLAlchemy | 2.0.35 | Data models for 13 tables |
| Spatial ORM | GeoAlchemy2 | 0.15.1 | POINT / MULTIPOLYGON geometry fields |
| Database | PostgreSQL + PostGIS | 14+ / 3.5 | Spatial data storage & indexing |
| Data validation | Pydantic + pydantic-settings | 2.9.0 | Request/response models + .env config class |
| **Agent orchestration** | **LangGraph (StateGraph)** | 0.2.64 | 8-node state graph: parallel fan-out/join + review loop + HITL approval gate |
| **LLM framework** | **LangChain + langchain-openai** | 0.3.17 | ChatOpenAI / OpenAIEmbeddings |
| **LLM reliability** | **Unified invocation layer (llm_invoker)** | — | Retry (1s/2s/4s) → circuit breaker (3 fails/60s) → provider-chain failover |
| **State persistence** | **langgraph-checkpoint-postgres + psycopg[binary]** | 2.0.15 / 3.3.6 | PostgresSaver checkpoints (auto-degrades to MemorySaver) |
| **Rerank** | **DashScope qwen3-rerank** | — | Hybrid-retrieval re-ranking, RRF-fusion fallback on failure |
| **Tool protocol** | **MCP (mcp + langchain-mcp-adapters)** | 2.2.0 / 0.2.0 | AMap weather read-only data source (FastMCP stdio) |
| **Observability** | **Langfuse (self-hosted, optional)** | 4.15.6 | Full-trace LangGraph callbacks |
| Text splitting | langchain-text-splitters | 0.3.5 | RecursiveCharacterTextSplitter (Chinese separators preferred) |
| PDF parsing | pdfplumber / pypdf / PyMuPDF / RapidOCR | — | Four-layer fallback text extraction (incl. OCR for scanned pages) |
| Vector store | pgvector | 0.3.6 | Reserved for vector column upgrade |
| Auth | bcrypt + python-jose | 4.2.1 / 3.3.0 | Password hashing + JWT HS256 |
| Spatial computation | geopandas / shapely | 1.0.1 / 2.0.5 | Grid clustering, buffer analysis |
| Data processing | pandas / numpy | 2.2.2 / 1.26.4 | Data import & aggregation |
| HTTP / upload | httpx / aiofiles / python-multipart | — | Async requests / file upload |

**LLM services (three providers switchable + fixed Bailian multimodal)**:

| Provider | Model Type | Model | Notes |
|---|---|---|---|
| Alibaba Bailian DashScope | Chat | qwen-plus | Primary provider, OpenAI-compatible mode |
| AMD GPU Cloud | Chat | DeepSeek-V4-Flash / Qwen3.8-Flash-Next | Backup provider (Qwen3.8 requires time-window validation) |
| Local Ollama | Chat | qwen2.5:7b | Offline & free |
| Alibaba Bailian (fixed) | Embedding | text-embedding-v3 | Decoupled from the Chat provider, unaffected by switching |
| Alibaba Bailian (fixed) | Vision | qwen-vl-plus | Fire image recognition, base64 multimodal messages |
| Alibaba Bailian (fixed) | Speech ASR | qwen3-asr-flash | chat/completions + input_audio data URI |
| Alibaba Bailian (fixed) | Speech TTS | qwen3-tts-flash | Native multimodal endpoint, text → wav |

> **Embedding / Vision / Speech models are always served by Alibaba Bailian**, fully decoupled from `ACTIVE_LLM_PROVIDER`.

---

## 3. Project Structure

```
fire_agent_back/
├── app/
│   ├── main.py                  ← Entry: lifespan creates tables + idempotent column backfill + seed admin + CORS + route registration
│   ├── core/
│   │   ├── config.py            ← Global config (pydantic-settings reads .env)
│   │   ├── database.py          ← SQLAlchemy engine / SessionLocal / Base
│   │   ├── security.py          ← bcrypt hashing + JWT encode/decode + get_current_user/admin
│   │   ├── llm.py               ← Multi-provider LLM routing (aliyun/amd/ollama) + Embedding
│   │   │                          + vision/ASR/TTS clients + list_provider_models
│   │   ├── llm_invoker.py       ← Unified LLM layer: retry/breaker/provider-chain failover/structured output/streaming/token audit
│   │   ├── checkpointer.py      ← LangGraph PostgresSaver checkpoints (degrades to MemorySaver)
│   │   ├── reranker.py          ← DashScope qwen3-rerank re-ranking (RRF fallback)
│   │   ├── mcp_client.py        ← MCP client (AMap weather tool, silent degradation)
│   │   ├── memory_store.py      ← User preference long-term memory (PostgresStore JSONB)
│   │   ├── observability.py     ← Langfuse callbacks (degrades to plain logging when disabled)
│   │   └── report_channels.py   ← Streaming report delta channel (SSE report_delta)
│   ├── models/                  ← 13 ORM tables
│   │   ├── user.py / fire_point.py / fire_risk.py / region_boundary.py
│   │   ├── emergency_resource.py / task.py / report.py
│   │   ├── kb_document.py / query_history.py / rag_history.py / vision.py
│   ├── schemas/                 ← Pydantic request/response models (auth/query/rag/agent/report/admin/dashboard)
│   ├── repositories/            ← fire_repository (fire points/predictions/boundaries) / report_repository
│   ├── services/
│   │   ├── query_service.py     ← Dual-engine intent recognition + three intent executors + GeoJSON generation
│   │   ├── rag_service.py       ← Upload/four-layer extraction/chunking/vectorization/hybrid retrieval/QA
│   │   └── data_service.py
│   ├── agents/
│   │   ├── orchestrator_agent.py ← LangGraph StateGraph (8 nodes: parallel fan-out/join + review loop + HITL approval)
│   │   ├── data_agent.py        ← Fire point query & aggregate statistics
│   │   ├── gis_agent.py         ← 0.1° grid clustering hotspots + buffer analysis
│   │   ├── rag_agent.py         ← Knowledge base retrieval node
│   │   └── report_agent.py      ← LLM five-part Markdown report (template fallback)
│   ├── workflows/               ← agent_workflow (LangGraph wrapper)
│   ├── utils/                   ← risk_level (level classification) / geojson
│   └── api/v1/routes/           ← 8 route modules
│       ├── auth.py / dashboard.py / query.py / rag.py
│       ├── agent.py / report.py / admin.py / media.py (vision & speech)
├── scripts/                     ← Data import & evaluation scripts
│   ├── init_db.py               ← Enable PostGIS + create tables
│   ├── import_fire_points.py    ← Yunnan_fire.json → historical_fire_points (5,411 records)
│   ├── import_predict_risks.py  ← Daily/monthly prediction JSON → predicted_fire_risks
│   ├── import_region_boundaries.py ← Yunnan_border.json → region_boundaries (16 prefectures)
│   ├── run_all_imports.py       ← One-click full import (custom paths + timing stats)
│   ├── eval_regression.py       ← Regression evaluation (golden set, 4 deterministic metrics, offline/live)
│   └── golden_set.json          ← Golden test cases for regression evaluation (10 cases)
├── mcp_server/
│   └── weather_server.py        ← MCP weather data source (FastMCP stdio: AMap geo→adcode→weather)
├── Dockerfile                   ← Backend image (python:3.12-slim + healthcheck)
├── docker-compose.yml           ← Full-stack orchestration (db/backend/frontend + optional Langfuse profile)
├── .env.example                 ← Environment variable template
├── sql/public.sql               ← Full database export (DDL + data)
├── data/knowledge_base/         ← Knowledge base upload storage (auto-created)
├── data/vision_uploads/         ← Fire-recognition image storage (uuid-named)
├── .env                         ← Runtime configuration
├── 整体实现.md                   ← Complete implementation doc in graduation-thesis style (architecture/ER/flowcharts)
└── requirements.txt
```

---

## 4. Core Features in Detail

### 4.1 Application Entry (main.py)

- `lifespan` startup hook: `create_all` auto-create tables → idempotent column backfill (compatible with old DBs) → seed admin (admin/123456)
- CORS middleware allows frontend 5173/4173
- 8 route modules mounted under `/api/v1/*`, Swagger docs: `http://localhost:8000/docs`

### 4.2 Smart Query (query.py + QueryService)

- **Dual-engine intent recognition**: LLM (qwen-plus, temperature=0.05, prompt built-in 16-prefecture list / season mapping / confidence enums, JSON output) + keyword regex fallback (prefecture short-name mapping "普洱"→"普洱市", "版纳"→"西双版纳傣族自治州"; "春季"→[3,4,5] months)
- **Three intent executors**: historical fire points (date range + FRP sort) / predicted fire risk (risk_score sort + risk-graded color GeoJSON) / data summary (Top city statistics)
- **History dedup**: dedup by user + query_text; repeated queries only update time and summary

### 4.3 RAG Knowledge Base (rag.py + RagService)

- **Four-layer PDF text extraction**: pdfplumber → pypdf → PyMuPDF text layer → RapidOCR image recognition (solves scanned pages/custom-font garbling, e.g. GB/T 36743-2018)
- **Chunking**: RecursiveCharacterTextSplitter (chunk_size=500, overlap=50, Chinese separators `\n\n → \n → 。 → ，` preferred)
- **Vectorization**: OpenAIEmbeddings (text-embedding-v3, Alibaba Bailian)
- **Hybrid retrieval**: Chinese word segmentation + vector cosine + keyword weighting (2-char words preferred) → **Rerank re-ranking** (qwen3-rerank; falls back to RRF fusion of the original order when disabled/failed), Top-K chunks; adaptive query rewriting for complex queries (up to 3 retrieval rounds)
- **QA**: LLM must cite source numbers; explicitly declares when no matching document is found; `POST /ask/stream` SSE streaming (meta→delta→done, partial output never persisted)

### 4.4 Multi-Agent Collaboration (agent.py + OrchestratorAgent)

LangGraph StateGraph state machine (v1.0.1 topology):

```
parse_task → (query_data → analyze_gis) ∥ retrieve_knowledge → join
           → generate_report → review_report →(≤2-round loop)→ approval_gate(HITL) → END
(Orchestrator)  (DataAgent)   (GisAgent)   (RagAgent)  (ReportAgent)  (Reviewer)   (interrupt/resume)
```

- **Plan-driven routing**: `parse_task` produces a structured TaskPlan; query_data / analyze_gis / generate_report are fixed steps (prevents "finished without a report"), the LLM only decides whether to add knowledge-base retrieval
- **Parallel fan-out/join**: query_data ∥ retrieve_knowledge run concurrently; the `operator.add` reducer writes increments only, merged at the join barrier
- **Reflective retry**: when a query returns empty, the LLM reflects, relaxes parameters and re-queries (≤2 rounds)
- **Review loop + hard guardrails**: low-temperature LLM review + LLM-independent hard guardrails with veto power (≥800 chars / required sections / real-data citations); rejected reports are rewritten with feedback (≤2 rounds)
- **HITL approval**: `approval_gate` interrupts via `interrupt` (status awaiting_approval); `POST /tasks/{id}/resume` injects approve / edit / reject and resumes on the same thread_id (interrupt state persisted by PostgresSaver)
- **Async tasks + SSE**: `POST /tasks` returns task_id immediately and executes in the background; node steps are written incrementally (running pre-write + terminal-state overwrite); `GET /tasks/{id}/stream?token=` pushes node-level progress / report deltas / terminal state via SSE (replay after disconnect, 1800s per-connection cap)
- **Seven-section rigid report template**: 一、执行摘要 Executive Summary / 二、数据来源与分析方法 Data Sources & Methodology / 三、火情数据分析 Fire Data Analysis / 四、高风险区域识别 High-Risk Area Identification / 五、重点巡防建议 Key Patrol Recommendations / 六、结论与展望 Conclusion & Outlook / 附：参考依据 Appendix: References (section titles and order are fixed, ≥800 chars, real-data citations, developer signature auto-appended); reports are auto-classified by query semantics as daily/weekly/monthly/special and support type filtering in the report center
- Tasks & steps (with JSON payloads) persist to `agent_tasks` / `agent_task_steps`; reports persist to `analysis_reports` (with llm_provider / llm_model / llm_tokens audit fields); soft delete for reports (user self-delete `hidden` / admin delete `deleted`), task detail `include_deleted` powers frontend history replay

### 4.5 System Admin (admin.py)

- **Config hot reload**: `setattr(settings, ...)` takes effect in memory + `dotenv.set_key` writes back to .env, **no restart needed**
- **Masking**: API Key `sk-***xxx` (first 3 / last 3), database URL only shows the part after `@`
- **Connection tests**: `/test/db` (SELECT 1), `/test/llm` (real invoke)
- **Bailian free-quota model catalog**: `GET /llm/models` calls the provider `/models` endpoint to validate availability in real time, cross-checks against the built-in free-quota catalog (5 categories: LLM/vision/multimodal/speech/embedding, 35 free models), sorted by "free first → longer validity → currently in use → verified", with masked key overview and console links; one-click 「Use」 switching for all model types (writes .env with hot reload)
- **System logs**: `log_system_event()` ring buffer of 200 entries
- **User management**: admin only; role change blocks self-modification, user deletion blocks self-deletion

### 4.6 Vision & Speech Module (media.py · /api/v1/vision)

**AI fire image recognition**:

- `POST /analyze`: upload jpg/png/webp/bmp (≤10MB) → base64 multimodal message (built-in forest fire monitoring expert prompt) → vision model outputs **four-part structured Markdown** (fire determination: visible flame/smoke/no anomaly / scene description / severity: minor–critical four levels / handling suggestions); non-fire images are explicitly labeled
- Image stored under `data/vision_uploads/` with uuid name, recognition result persisted to `vision_history` (user-isolated)
- History list/detail/delete/image authenticated stream (`GET /image/{id}`) all enforce user data isolation

**Speech Recognition (ASR) & Speech Synthesis (TTS)**:

| Capability | Endpoint | Implementation |
|---|---|---|
| Speech recognition | `POST /audio/transcriptions` | Bailian `chat/completions` + `input_audio` **data URI** format (raw base64 reports "URL invalid"); wav/mp3/opus/aac/amr, ≤20MB |
| Speech synthesis | `POST /audio/speech` | Bailian **native** multimodal-generation endpoint (compat mode has no /audio/speech), `voice` (Cherry) required, downloads audio URL as wav stream; text limited to 500 chars |

> ASR / TTS are fixed to Bailian (ASR_MODEL / TTS_MODEL), unaffected by ACTIVE_LLM_PROVIDER switching; the vision model routes by VISION_PROVIDER (aliyun Bailian / amd GPU Cloud); returns a friendly message without throwing when no key is configured.

### 4.7 LLM Multi-Provider Routing (core/llm.py)

```
get_llm() ─── ACTIVE_LLM_PROVIDER (.env / online switch in admin page)
   ├─ aliyun → ChatOpenAI(Bailian compat endpoint, qwen-plus)
   ├─ amd    → ChatOpenAI(AMD endpoint, DeepSeek-V4-Flash)
   └─ ollama → ChatOpenAI(localhost:11434/v1, qwen2.5:7b)

get_embedding()     ─── always Alibaba Bailian text-embedding-v3
get_vision_llm()    ─── routed by VISION_PROVIDER (aliyun Bailian / amd GPU Cloud)
transcribe_audio()  ─── always Alibaba Bailian ASR_MODEL (qwen3-asr-flash)
synthesize_speech() ─── always Alibaba Bailian TTS_MODEL (qwen3-tts-flash)
list_provider_models() → calls each provider's /models endpoint to validate key-accessible models
```

> **v1.0.1**: all business code calls the LLM through `app/core/llm_invoker.py` (`invoke_llm` / `invoke_structured` / `stream_llm`), which layers exponential-backoff retry → circuit breaker (3 fails / 60s cooldown) → provider-chain degradation → rule-based fallback, and carries provider / model / tokens / degraded audit fields; `get_llm` is now only a low-level factory and new code must not call it directly.

---

## 5. Database Design

The database has **13 business tables** (plus PostGIS system tables); full DDL is in `sql/public.sql`:

| Category | Table | Description | Data Scale |
|---|---|---|---|
| Business data | `historical_fire_points` | Historical fire points (geom POINT 4326, frp, confidence; date/city/confidence indexes) | **5,411 records** |
| Business data | `predicted_fire_risks` | Predicted fire risk (daily/monthly dual views, fire_level 1-5, risk_score) | 2025—2026 full |
| Business data | `region_boundaries` | 16 prefecture boundaries (MULTIPOLYGON 4326) | 16 records |
| Business data | `emergency_resources` | Emergency resources (reserved) | To be imported |
| Platform data | `users` | Users (bcrypt hash, role user/admin) | Grows with registrations |
| Platform data | `query_history` | Query history (dedup by user + text) | Grows with usage |
| Platform data | `rag_history` | RAG QA history | Grows with usage |
| Platform data | `agent_tasks` | Agent tasks (status/report_id FK) | Grows with usage |
| Platform data | `agent_task_steps` | Task steps (JSON payloads, one-to-many cascade delete) | Grows with usage |
| Platform data | `analysis_reports` | Analysis reports (Markdown content) | Grows with usage |
| Platform data | `kb_documents` | KB documents (state machine pending→processing→ready/failed) | Grows with uploads |
| Platform data | `kb_chunks` | KB chunks (content/token_count/embedding) | Grows with uploads |
| Platform data | `vision_history` | AI fire recognition history (image path + Markdown result + model name) | Grows with recognitions |

**Relations**: `agent_tasks 1—N agent_task_steps`, `agent_tasks N—1 analysis_reports`, `kb_documents 1—N kb_chunks`, `users 1—N query_history/rag_history/agent_tasks/analysis_reports/kb_documents/vision_history`.

E-R diagram and full table structure details are in the Implementation doc (Chapter 5).

---

## 6. API Reference

Unified response format: `{ code, message, data }`.

### Auth `/api/v1/auth`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/register` | - | Register (dedup + bcrypt + JWT, logged in right after registration) |
| POST | `/login` | - | Login (JWT 24h) |
| GET | `/me` | Bearer | Current user info |

### Dashboard `/api/v1/dashboard`

| Method | Path | Description |
|---|---|---|
| GET | `/history-fires` | Historical fire points (date/city/confidence/pagination, max 5,000) |
| GET | `/predict-risks` | Predicted fire risk (year/month/day/daily\|monthly/city) |
| GET | `/summary` | Summary stats (total/high-confidence/avg FRP/Top 5 cities) |

### Smart Query `/api/v1/query`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/parse` | - | Intent parsing only (LLM/keyword) |
| POST | `/execute` | - | Parse + execute + four-dimensional result + history persistence |
| GET | `/history` | Bearer | Current user query history (user-isolated) |
| DELETE | `/history/{id}` | Bearer | Delete a single history record |

### Knowledge Base `/api/v1/rag`

| Method | Path | Description |
|---|---|---|
| POST | `/ask` | RAG QA (answer + citations + llm_used) |
| POST | `/ask/stream` | **RAG streaming QA** (SSE: meta→delta→done) |
| GET | `/history` | QA history (user-isolated) |
| DELETE | `/history/{id}` | Delete QA history |
| POST | `/documents` | Upload document (multipart, category form field) |
| GET | `/documents` | Document list (user-isolated) |
| DELETE | `/documents/{id}` | Delete document (file + chunk cascade) |

### Agent `/api/v1/agent`

| Method | Path | Description |
|---|---|---|
| POST | `/tasks` | Create task (**returns task_id immediately, executes in background**) |
| GET | `/tasks` | Task list (with report provider / detailed model name) |
| GET | `/tasks/{task_id}` | Task detail (execution steps + report, history replay) |
| GET | `/tasks/{task_id}/stream?token=` | **SSE real-time progress** (node steps / report deltas / approval / terminal state, replay after disconnect) |
| POST | `/tasks/{task_id}/resume` | **HITL approval resume** (approve / edit / reject) |
| DELETE | `/tasks/{task_id}` | Delete task (cascade steps) |
| GET | `/capabilities` | "System capabilities" panel (real runtime state of orchestration / breaker / checkpoints / MCP / observability) |
| GET | `/status` | Status of the 5 Agents |

### Reports `/api/v1/reports`

| Method | Path | Description |
|---|---|---|
| GET | `/list` | List (page/page_size/report_type, user-isolated) |
| GET | `/{id}` | Detail (Markdown content) |
| POST | `/generate` | Generate/save report |
| DELETE | `/{id}` | Delete report |
| GET | `/export/{id}?format=md\|html` | Export (md attachment / HTML print template) |

### System Admin `/api/v1/admin`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/status` | Login | Runtime status overview |
| GET | `/config` | Login | Current config (**masked**) |
| POST | `/config` | Login | Update config (**writes .env with hot reload**) |
| POST | `/test/db` | Login | Database connection test |
| POST | `/test/llm` | Login | LLM connection test (real invoke) |
| GET | `/logs?limit=` | Login | System logs (ring buffer of 200) |
| GET | `/llm/models?provider=` | Login | Provider model list + Bailian free-quota catalog (5 categories) + key overview |
| GET | `/users` | **Admin** | User list |
| PUT | `/users/{id}/role` | **Admin** | Change role (self-change blocked) |
| DELETE | `/users/{id}` | **Admin** | Delete user (self-delete blocked) |

### Vision & Speech `/api/v1/vision`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/analyze` | Bearer | **Fire image recognition** (qwen-vl multimodal, persisted to vision_history) |
| GET | `/history` | Bearer | Recognition history list (user-isolated, max 100) |
| GET | `/history/{id}` | Bearer | Recognition history detail |
| DELETE | `/history/{id}` | Bearer | Delete recognition record (incl. local image) |
| GET | `/image/{id}` | Bearer | Authenticated image stream (FileResponse) |
| POST | `/audio/transcriptions` | Bearer | **Speech recognition ASR** (wav → text, qwen3-asr-flash) |
| POST | `/audio/speech` | Bearer | **Speech synthesis TTS** (text → wav audio stream, qwen3-tts-flash) |

### Others

| Method | Path | Description |
|---|---|---|
| GET | `/` | Service info |
| GET | `/health` | Health check |
| GET | `/docs` | Swagger interactive docs |

---

## 7. Environment Requirements

| Component | Requirement |
|---|---|
| OS | Windows / Linux / macOS |
| Python | **3.10+** (a dedicated conda env is recommended) |
| PostgreSQL | 14+ with **PostGIS** extension enabled |
| Network | Needs access to Alibaba Bailian / AMD endpoints (offline can switch to local Ollama) |
| Containerization (optional) | Docker + Docker Compose (one-click db/backend/frontend, optional Langfuse observability profile) |

---

## 8. Quick Start

### 8.0 Docker Compose One-Click Deployment (new in v1.0.1, recommended)

```bash
cp .env.example .env          # Prepare environment variables (fill in real keys)
docker compose up -d          # Bring up the full stack: postgis/db + backend + frontend
docker compose --profile observability up -d   # Optional: add self-hosted Langfuse observability
```

- Backend `Dockerfile`: python:3.12-slim + dependency-layer caching + `/health` healthcheck;
- The frontend image ships an nginx config: the `/api` reverse proxy **disables buffering (proxy_buffering off) with a 1800s timeout**, so SSE real-time progress / report deltas / RAG streaming are never buffered;
- backend starts automatically after the db healthcheck turns ready (in-container DATABASE_URL overridden to host `db`), data persisted in volumes;
- Once up: frontend at `http://localhost:8080`, backend Swagger at `http://localhost:8000/docs`.

### 8.1 Prepare the Database (one-time)

1. Install PostgreSQL 14+, enable the PostGIS extension;
2. Create an empty database `fire_agent`:

```sql
CREATE DATABASE fire_agent;
-- After switching to fire_agent:
CREATE EXTENSION IF NOT EXISTS postgis;
```

### 8.2 Install Dependencies & Configure

```bash
# 1. Create and activate a Python environment
conda create -n fire_agent_back python=3.10
conda activate fire_agent_back

# 2. Enter the project directory and install dependencies
cd fire_agent_back
pip install -r requirements.txt

# 3. Create .env in the project root (see Section 10 for configuration)
```

### 8.3 Import Data & Start

```bash
# 4. One-click data import (tables → boundaries → fire points → predictions)
python scripts/run_all_imports.py

# 5. Start the service
uvicorn app.main:app --reload --port 8000
```

After a successful start:

- Service URL: `http://localhost:8000`
- Swagger docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`
- **Default admin**: `admin / 123456` (auto-created on first start, skipped if it already exists)

### 8.4 Start the Frontend (companion)

```bash
cd fire_agent_front
npm install
npm run dev          # http://localhost:5173
```

---

## 9. Data Import

### Data Sources

| Data | Source | Scale |
|---|---|---|
| Historical fire points | NASA FIRMS MODIS (Yunnan) | **5,411 records** (incl. FRP/confidence/day-night/brightness temperature) |
| Predicted fire risk | GTWR model predictions | 2025—2026 daily + monthly, incl. fire_level 1-5 |
| Administrative boundaries | Yunnan 16-prefecture GeoJSON | 16 MULTIPOLYGONs |

### Import Scripts

| Script | Function |
|---|---|
| `scripts/init_db.py` | Enable PostGIS extension + create all tables |
| `scripts/import_fire_points.py` | Yunnan_fire.json → historical_fire_points (incl. geom construction) |
| `scripts/import_predict_risks.py` | Daily/monthly JSON → predicted_fire_risks |
| `scripts/import_region_boundaries.py` | Yunnan_border.json → region_boundaries (SRID=4326) |
| `scripts/run_all_imports.py` | **One-click full import** (tables→boundaries→fire points→predictions, supports custom paths like `--fire-path`, with timing stats) |

```bash
# One-click full import
python scripts/run_all_imports.py
```

> You can also restore the database directly from `sql/public.sql` (full DDL + data export) via Navicat / psql.

---

## 10. Configuration (.env)

Create a `.env` file in the project root:

```env
# Database (PostGIS must be enabled)
DATABASE_URL=postgresql://postgres:password@localhost:5432/fire_agent

# JWT signing secret (change in production)
JWT_SECRET=your-strong-secret

# AMap (weather API)
AMAP_KEY=your-key

# Active LLM provider: aliyun | amd | ollama
ACTIVE_LLM_PROVIDER=aliyun

# Alibaba Bailian (Chat + Embedding, OpenAI-compatible mode)
LLM_API_KEY=sk-xxxxxxxx
LLM_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-plus
EMBEDDING_MODEL=text-embedding-v3

# Vision / Speech models (ASR/TTS fixed to Bailian; vision switchable via VISION_PROVIDER)
VISION_MODEL=qwen-vl-plus
ASR_MODEL=qwen3-asr-flash
TTS_MODEL=qwen3-tts-flash

# AMD GPU Cloud (backup Chat provider)
AMD_API_KEY=your-key
AMD_API_BASE=https://developer.amd.com.cn/radeon/v1
AMD_MODEL=DeepSeek-V4-Flash

# Qwen3.8-Flash-Next availability window (YYYY-MM-DD HH:MM:SS, empty = unlimited)
QWEN3_8_FLASH_START=
QWEN3_8_FLASH_END=

# Local Ollama (offline backup)
OLLAMA_API_BASE=http://localhost:11434/v1
OLLAMA_MODEL=qwen2.5:7b

# RAG knowledge base
KB_UPLOAD_DIR=data/knowledge_base
KB_CHUNK_SIZE=500
KB_CHUNK_OVERLAP=50
KB_TOP_K=5

# Rerank re-ranking (DashScope qwen3-rerank, uses LLM_API_KEY; auto-degrades to RRF fusion on failure)
RERANK_ENABLED=true
RERANK_MODEL=qwen3-rerank

# Agent parameter: reports require manual approval (HITL) before finalization
AGENT_REQUIRE_APPROVAL=true

# P2 feature switches
LLM_STREAM_ENABLED=true      # End-to-end streaming (reports / RAG answers pushed incrementally)
PREFERENCES_ENABLED=true     # User preference long-term memory (PostgresStore)
MCP_ENABLED=true             # MCP AMap weather read-only data source (skipped silently on failure)

# Langfuse self-hosted observability (degrades to plain logging when disabled or no keys)
LANGFUSE_ENABLED=false
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=

# Vision provider (vision switchable aliyun/amd; ASR/TTS always Bailian)
VISION_PROVIDER=aliyun
```

**Configuration notes**:

- **All LLM parameters are optional**: when LLM_API_KEY is empty the system auto-degrades (keyword parsing / template reports); non-AI features such as dashboard, maps, charts, and report management remain fully usable;
- Model config can also be filled online instead of .env, in the frontend "System Admin → Model Access" page; **saving writes to .env and hot-reloads (no restart)**, with masked echo; you can also one-click switch any model type (Chat/vision/ASR/TTS/Embedding) through the Bailian free-quota catalog;
- AMD model names must exactly match the available model names returned by AMD's `/models` endpoint (e.g. `DeepSeek-V4-Flash`), otherwise 404;
- **Embedding / Speech models are always served by Alibaba Bailian** (using LLM_API_KEY), independent of ACTIVE_LLM_PROVIDER; the vision model defaults to Bailian and can be switched to AMD via VISION_PROVIDER;
- **ASR/TTS requires the Bailian LLM_API_KEY**: speech recognition uses `chat/completions + input_audio`, speech synthesis uses the Bailian native multimodal endpoint; they are not compatible with other providers' compatible endpoints;
- **P2 switches degrade safely**: RERANK_ENABLED / LLM_STREAM_ENABLED / PREFERENCES_ENABLED / MCP_ENABLED / LANGFUSE_ENABLED all auto-degrade when disabled or dependencies are missing, without affecting core features; Langfuse supports self-hosted deployment via `docker compose --profile observability`.

---

## 11. FAQ

| Problem | Solution |
|---|---|
| Startup database connection failure | Check that PostgreSQL is running, the DATABASE_URL password in `.env` is correct, and the `fire_agent` database has been created |
| `CREATE EXTENSION postgis` error | Install the PostGIS extension package first (tick it in the Windows installer / Linux: `apt install postgresql-14-postgis-3`) |
| AMD model connection 404 | Model name does not match the AMD `/models` endpoint; switch to an available model name `DeepSeek-V4-Flash` |
| PDF extraction garbled | Custom-font-encoded PDFs go through the OCR fallback (PyMuPDF render + RapidOCR); make sure `rapidocr-onnxruntime` is installed |
| OCR dependency install failure | `pip install rapidocr-onnxruntime` (downloads onnx models on first run, requires network) |
| Smart query uses keywords instead of LLM | LLM_API_KEY not configured or the LLM call failed and auto-degraded; configure and test the connection in "System Admin → Model Access" |
| Speech recognition reports "URL invalid" | ASR audio must be embedded in input_audio as a data URI (`data:audio/wav;base64,...`); raw base64 is not accepted by Bailian; frontend speech.js already encodes WAV this way |
| Speech synthesis 404 / unsupported | Bailian's OpenAI-compatible mode has no /audio/speech endpoint; the system uses the native multimodal-generation endpoint instead; confirm TTS_MODEL is qwen3-tts-flash or cosyvoice-v2 |
| Fire recognition returns "API Key not configured" | The vision model uses the Bailian LLM_API_KEY by default (or AMD_API_KEY after switching VISION_PROVIDER to amd); configure the corresponding key in "System Admin → Model Access" and retry (VISION_MODEL defaults to qwen-vl-plus) |
| Frontend CORS error | In development the Vite proxy handles it; in production configure an `/api` reverse proxy in Nginx, or modify CORS_ORIGINS |
| Changing .env has no effect | Editing the file directly requires a restart; use "System Admin → Model Access" to save (writes .env + in-memory, no restart) |
| SSE progress not pushed / disconnects early | The reverse proxy must disable buffering for `/api` (`proxy_buffering off`) and relax read timeouts (see the 1800s config in the frontend repo's nginx.conf); EventSource passes the JWT via `?token=` |
| MCP weather not taking effect | Make sure MCP_ENABLED=true and `mcp` / `langchain-mcp-adapters` are installed; when AMAP_KEY is missing or the call fails it is skipped silently without blocking report generation |

---

*Developer: wjl (19136220923@163.com) · Backend source: https://gitee.com/wjl2004/fire_agent_back · Frontend source: https://gitee.com/wjl2004/fire_agent_front*
