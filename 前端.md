# 焰哨 FlameSentry · 智慧火险预警与多智能体协作平台 —— 前端（fire_agent_front）

> **当前版本**：v1.0.1（v1.0.0 基线之上新增 3D 数字孪生大屏 / 明暗双主题 / Agent SSE 流式进度与 HITL 审批 / 流式 RAG 问答 / 个人中心等，详见 [9. 版本记录](#9-版本记录)）
> 本项目是「焰哨 FlameSentry · 智慧火险预警与多智能体协作平台」（现实使用名：**焰哨多Agent与可视化平台**）的前端部分，基于 **Vue 3 + Vite + OpenLayers + Three.js + ECharts + Element Plus** 构建。
> 配套后端：[fire_agent_back](https://gitee.com/wjl2004/fire_agent_back)（FastAPI + PostgreSQL/PostGIS + LangChain/LangGraph）
> 完整的系统设计文档见后端仓库《整体实现.md》。
> **在线演示**：https://wjl2004.ffuf.cn/（手机上可能会把这个网址ban掉）    or    https://8.156.67.47/login
> **演示账户**：test  123456
> **GitHub 仓库**：https://github.com/wjl-cong/fire_agent（⭐ 欢迎 Star）

---

## 目录

1. [项目简介](#1-项目简介)
2. [技术栈](#2-技术栈)
3. [项目结构](#3-项目结构)
4. [页面功能详解](#4-页面功能详解)
5. [环境要求](#5-环境要求)
6. [快速启动](#6-快速启动)
7. [构建与部署](#7-构建与部署)
8. [常见问题](#8-常见问题)
9. [版本记录](#9-版本记录)

---

## 1. 项目简介

前端为**前后端分离架构**的 SPA 应用，共 8 个页面路由，覆盖火险治理全流程：

| 页面           | 路由                | 权限               | 核心能力                                                                                                                                  |
| -------------- | ------------------- | ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| 登录/注册      | `/login`          | 公开               | JWT 登录、注册即登录、redirect 回跳                                                                                                       |
| 作战大屏       | `/dashboard`      | 登录               | 历史火点/预测火险/边界/热力图/聚合/量测/导出 PNG + 4 图表；**2D/3D 地图一键切换**（Three.js 3D 数字孪生）；**左侧 AI 火情识别侧栏**（视觉模型识别 + 历史回看 + MD 渲染 + 语音播报） |
| 智能查询       | `/smart-query`    | 登录               | 自然语言 → LLM 解析 → 摘要/表格/图表/地图四维联动，查询历史后端持久化（同文本去重）；**🎤 语音输入自动查询 + 🔊 摘要播报**          |
| 知识库         | `/knowledge-base` | 登录               | 文档上传管理 + RAG 问答（**流式打字机 + 非流式兜底**）+ 引用来源展示；**🎤 语音提问 + 🔊 回答播报**                                 |
| Agent 协作中心 | `/agent-center`   | 登录               | 5 Agent 流水线 **SSE 节点级流式进度 + HITL 人工审批（通过/编辑/驳回）+ 任务历史完整回放**；**🎤 语音下发任务 + 🔊 报告播报**          |
| 报告中心       | `/report-center`  | 登录               | 报告列表/详情/类型筛选/**模型名徽标**/导出 Markdown/HTML/打印 PDF（删除为软删）；**🔊 报告语音播报**                                |
| 个人中心       | `/profile`         | 登录               | 顶栏头像入口，修改邮箱/修改密码                                                                                                            |
| 系统管理       | `/admin`          | **仅 admin** | 系统总览/数据源/模型接入（视觉/语音模型 + 百炼免费额度目录 + AMD 实时目录 + 额度快照）/Agent 参数/日志/用户管理                             |

**设计特色**：

- **Agent 风味贯穿全系统**：大屏显示 DataAgent 数据管线状态与 VisionAgent 火情识别侧栏、查询页展示 QueryAgent 解析过程、知识库展示 RagAgent 检索过程、报告中心标识 ReportAgent 生成来源；
- **3D 数字孪生大屏（v1.0.1）**：`components/Map3D.vue`（Three.js，sc-datav 风格）——州市面片挤出 + 侧面扫光 shader + 贝塞尔飞线 + 火点屏幕空间聚类柱状图（40px 贪心聚类，与 2D OL Cluster 缩放行为镜像联动），与 2D OpenLayers 一键切换；
- **SSE 流式 Agent + HITL 人机协同（v1.0.1）**：Agent 执行全程 `EventSource` 节点级流式推送（断线自动降级拉详情），报告草稿经人工「通过/编辑/驳回」审批后才定稿落报告中心；
- **明暗双主题（v1.0.1）**：`stores/theme.js` + `style/gis-theme.css` CSS 变量 token 全站自动适配，玻璃卡化风格 + sc-datav 英文角标；
- **全链路语音交互**：`utils/speech.js` 统一封装录音（Web Audio API 采集 PCM → 纯前端编码 WAV）与播报（TTS 音频流播放），五个 AI 页面 🎤 输入自动执行、🔊 结果一键播报；
- **降级兜底**：大屏后端 API 失败自动降级本地 JSON，核心页面永不白屏；
- **统一交互**：左侧面板"点击标题栏展开/折叠"在查询/知识库/Agent/报告/火情识别五处统一，删除按钮常显 + `@click.stop` 防误触；
- **等级同源**：5 级火险颜色/文案统一由 `utils/riskLevel.js` 管理，与后端分档完全一致。

---

## 2. 技术栈

| 类别      | 技术                     | 版本    | 用途                                                |
| --------- | ------------------------ | ------- | --------------------------------------------------- |
| 框架      | Vue 3（Composition API） | ^3.5.13 | 全部页面使用`<script setup>`                      |
| 路由      | Vue Router               | ^4.5.0  | 8 条路由 + 登录/管理员守卫                          |
| 状态管理  | Pinia                    | ^3.0.1  | auth store + theme store（token/user/主题持久化）   |
| UI 组件库 | Element Plus             | ^2.9.6  | 表格/分页/上传/消息/确认框（中文语言包 + 自动导入） |
| 地图引擎  | OpenLayers               | ^10.4.0 | 天地图底图、火点聚合、热力图、边界、绘制量测        |
| 3D 引擎   | **Three.js**       | ^0.186.1 | 首页 3D 数字孪生大屏（挤出面片/飞线/聚类柱/CSS2D 标签） |
| 空间计算  | Turf.js                  | ^7.2.0  | 绘制面积 / 距离量测                                 |
| 图表      | ECharts                  | ^5.6.0  | 大屏 4 图表 + 智能查询结果图表（GIS 暗色主题）      |
| 热力渲染  | webgl-heatmap            | ^0.2.3  | 火点密度热力图                                      |
| 构建工具  | Vite + Sass              | ^6.1.0  | dev server +`/api` 代理到后端 8000                |
| 辅助库    | file-saver / moment      | —      | 地图导出、时间处理                                  |
| 代码质量  | ESLint 9 + oxlint        | dev     | 双 lint（`npm run lint`）                         |

---

## 3. 项目结构

```
fire_agent_front/
├── vite.config.js              ← Vite 配置：/api 代理到 http://localhost:8000，
│                                   Element Plus 自动导入插件，@ 别名指向 src
├── package.json                ← 依赖与启动脚本
└── src/
    ├── main.js                 ← 入口：注册 Pinia / Router / Element Plus 中文包，
    │                              OpenLayers Canvas willReadFrequently patch；首屏提前应用主题
    ├── App.vue                 ← 轻量路由容器
    ├── router/index.js         ← 8 条路由 + 全局守卫（登录鉴权 + admin 权限）
    ├── stores/auth.js          ← Pinia 认证状态（login/register/logout，localStorage 持久化）
    ├── stores/theme.js         ← Pinia 主题状态（明暗切换，html.dark + localStorage）
    ├── layout/MainLayout.vue   ← 48px 窄侧边栏（iconfont 图标 + adminOnly 菜单过滤
    │                              + ☾/☀ 主题切换按钮 + 头像进入个人中心）
    ├── api/dashboard.js        ← 大屏 API 封装（fetchHistoryFires/fetchPredictRisks/fetchSummary）
    ├── utils/
    │   ├── authFetch.js        ← 统一认证 fetch：自动附 Bearer，401 登出跳登录
    │   ├── speech.js           ← 语音交互：Web Audio API 录音 PCM→WAV 编码（ASR）
    │   │                          + TTS 播报（speakText/speakState/startRecord）
    │   ├── markdown.js         ← Markdown 安全渲染（标题/表格/代码/列表/引用，HTML 转义）
    │   ├── riskLevel.js        ← 5 级火险颜色/文案（与后端分档一致）
    │   ├── themeTokens.js      ← JS 侧读取主题 CSS 变量（ECharts/3D 实时取色）
    │   ├── parseGeoData.js     ← GeoJSON 解析
    │   ├── draw.js / computed.js / downLoad.js / timeWeather.js / setPointStyle.js
    │   └── echartsGisTheme.js  ← ECharts GIS 暗色主题
    ├── components/
    │   ├── map.vue             ← OpenLayers 2D 核心地图组件（天地图底图/聚合/热力/边界/高亮图层）
    │   ├── Map3D.vue           ← Three.js 3D 数字孪生大屏（sc-datav 风格：挤出面片/扫光 shader/
    │   │                          贝塞尔飞线/火点屏幕空间聚类柱/CSS2D 标签/明暗双主题）
    │   ├── clock.vue           ← 实时时钟
    │   ├── SystemCapabilities.vue ← 系统能力面板（GET /agent/capabilities，Agent 中心右列）
    │   └── chart/              ← 4 个大屏图表组件
    │       ├── historicalFireHazardLevel.vue    ← 历史火险等级分布
    │       ├── historicalFireFrequency.vue      ← 历史火点频次
    │       ├── proportionFireRiskWarnings.vue   ← 预测火险预警占比
    │       └── distributionFireRiskWarning.vue  ← 预测火险分布
    ├── views/
    │   ├── login/index.vue         ← 登录/注册双模式
    │   ├── dashboard/index.vue     ← 作战大屏（约 2310 行，含 2D/3D 切换）
    │   ├── smart-query/index.vue   ← 智能查询
    │   ├── knowledge-base/index.vue← 知识库 RAG（流式问答）
    │   ├── agent-center/index.vue  ← Agent 协作中心（SSE 流式 + HITL 审批）
    │   ├── report-center/index.vue ← 报告中心
    │   ├── profile/index.vue       ← 个人中心（改邮箱/改密码）
    │   └── admin/index.vue         ← 系统管理（6 Tab，仅管理员）
    ├── style/
    │   ├── gis-theme.css       ← 明暗双主题（CSS 变量 token，html.dark 切换）
    │   └── common.css
    └── assets/                 ← 本地兜底数据：Yunnan_fire.json / Yunnan_border.json /
                                    predict_2025_2026_daily.json / predict_2025_2026_month.json
```

---

## 4. 页面功能详解

### 4.1 登录 / 注册页（`/login`）

- 登录/注册双模式一键切换，表单校验（用户名 ≥2 字符、密码 ≥6 位、两次密码一致）
- 登录/注册成功后自动登录（JWT 存 localStorage），按 `?redirect=` 回跳原页面
- 深色玻璃拟态卡片 UI

### 4.2 作战大屏（`/dashboard`）

- **数据流**：`Promise.all` 并发请求历史火点（5000 条上限）/逐日预测/逐月预测，任一失败自动降级本地 JSON
- **2D 地图**（OpenLayers）：天地图底图、火点聚合（Cluster distance=40，点击弹出 el-drawer 详情）、webgl 热力图、16 州市边界、多边形/线绘制 + Turf.js 量测、导出 PNG
- **3D 数字孪生地图**（`Map3D.vue`，Three.js，v1.0.1）：州市面片挤出 + 侧面扫光 shader + 贝塞尔飞线 + 火点屏幕空间聚类柱（40px 贪心聚类，与 2D 行为镜像联动）+ ExtrudeGeometry 实心基座垫块；明暗双主题、入场俯冲 2.2s、悬停抬升、`city-click` 高亮 2D 图层；顶栏 2D/3D 一键切换
- **图表**（ECharts）：历史火险等级分布 / 历史火点频次 / 预测火险预警占比 / 预测火险分布
- **顶栏**：实时时钟、高德天气 API、逐日/逐月视图切换、**DataAgent 数据管线状态**（与天气垂直堆叠，不挤压左侧按钮）
- **左侧 AI 火情识别侧栏**（可折叠 34px ↔ 310px）：拖拽上传火场照片 → 视觉模型（qwen-vl）识别 → 结果 **Markdown 渲染**（火情判定/场景描述/严重程度/处置建议）→ 🔊 语音播报；识别历史列表点击回看（鉴权图片流），单条删除

### 4.3 智能查询（`/smart-query`）

- 自然语言输入（textarea + Ctrl+Enter + 4 个示例标签）+ **🎤 语音输入**（录音 → ASR 识别 → 自动执行查询）
- **QueryAgent 解析面板**：意图 / 结构化参数 chips / LLM·关键词解析方式徽标 / 解析说明
- **四维结果联动**：摘要卡片（🔊 语音播报）/ 表格（动态列 el-table）/ 图表（柱·折·饼）/ 地图（GeoJSON 风险分档配色 + 自适应缩放）
- **查询历史侧栏**：展开/折叠（48px ↔ 220px）、落库后端（同文本自动去重）、按用户隔离、单条删除、LLM/关键词标注

### 4.4 知识库 RAG（`/knowledge-base`）

- **左侧文档面板**（56px ↔ 280px 折叠）：拖拽/点击上传（PDF/TXT/MD）、状态徽标、单条删除
- **右侧问答区**：示例问题、🎤 语音提问（识别完成自动提交）、回答卡片（LLM/关键词徽标 + 🔊 语音播报）、**引用来源列表**（相关性分数 + 点击展开全文）
- **流式问答（v1.0.1）**：优先走 `POST /rag/ask/stream`（SSE 打字机增量渲染，来源引用随流结束附上），流式失败/不支持自动回退非流式接口兜底

### 4.5 Agent 协作中心（`/agent-center`）

- 任务输入（textarea + Ctrl+Enter + 4 个示例任务）+ 🎤 语音输入（识别完成自动执行任务）
- **Agent 系统状态条**：5 个 Agent 就绪状态点
- **5 步流水线可视化**：拆解任务 → 查询数据 → 分析 GIS → 检索知识 → 生成报告，步骤逐个点亮（completed 绿 / running 黄脉冲 / pending 灰）
- **SSE 节点级流式进度（v1.0.1）**：`EventSource` 订阅 `GET /agent/tasks/{id}/stream?token=<JWT>`，实时接收节点进度与 `report_delta` 报告增量（打字机渲染）；SSE 断开自动降级拉取任务详情兜底
- **HITL 人工审批（v1.0.1）**：报告草稿生成后任务暂停（报告暂不落报告中心），右列审批卡展示草稿，支持**通过并定稿 / 以编辑稿定稿 / 驳回重写（附意见）**，审批后任务继续、报告定稿落报告中心
- **系统能力面板（v1.0.1）**：右列 `SystemCapabilities.vue` 展示后端 `GET /agent/capabilities` 能力清单（多 Provider/熔断器/Rerank/MCP/记忆等）
- **执行过程摘要** + Markdown 报告渲染（🔊 语音播报）+ ReportAgent 徽标
- **任务历史侧栏**（56px ↔ 260px）：落库后端、点击回放、单条删除；**回放链路**：本地缓存 → `GET /agent/tasks/{task_id}` 拉取持久化执行步骤（agent_task_steps）与关联报告 → "Agent 执行过程"面板完整还原

### 4.6 报告中心（`/report-center`）

- 左侧列表面板（60px ↔ 340px 折叠）：类型筛选（全部/日报/周报/月报/专项）+ 分页 + 类型徽标/标签/摘要 + 单条删除
- **模型名徽标（v1.0.1）**：列表与详情头部/元信息栏展示生成模型——`llm_model` 优先（如 qwen-max），无模型名回退供应商名「阿里百炼 / AMD GPU Cloud」
- **删除为软删（v1.0.1）**：用户自删仅对自己隐藏（管理员仍可见），管理员删除为全局软删
- 右侧详情：Markdown 正文渲染 + **🔊 语音播报（摘要 + 正文）/ 导出 Markdown / 导出 HTML / 打印另存 PDF / 删除**
- ReportAgent 徽标标识 Agent 自动生成的报告

### 4.7 系统管理（`/admin`，仅管理员）

| Tab        | 功能                                                                                                                                                                                                                                                                                                                 |
| ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 系统总览   | 版本、数据库状态、LLM 可用性、5 Agent 状态卡片（空值兜底）                                                                                                                                                                                                                                                           |
| 数据源     | 数据库地址（脱敏）+ 连接测试                                                                                                                                                                                                                                                                                         |
| 模型接入   | LLM 提供商切换（aliyun/amd/ollama）、API Key（脱敏`sk-***xxx`）、**视觉/ASR/TTS 模型配置**、保存即写 .env 热生效、LLM 真实 invoke 测试；**百炼免费额度模型目录**：5 大类 Tab（大语言/视觉/全模态/语音/向量），实时校验可用性，按"免费优先→有效期长→当前使用→已验证"排序，全类型模型一键「使用」切换；**AMD 实时模型目录（v1.0.1）**：实时抓取 AMD 官方 `tokenfactory` 目录（text/vision 分类 Tab）；**百炼额度快照（v1.0.1）**：计费文档免费额度目录（5 类）+ 账号配额快照表（剩余量/过期时间/状态，按过期时间排序） |
| Agent 参数 | 编排温度 / 报告温度 / 最大 Agent 数                                                                                                                                                                                                                                                                                  |
| 系统日志   | 环形缓冲 200 条（Agent 任务/配置变更/用户管理/连接测试），**30s 轮询自动刷新（v1.0.1）**                                                                                                                                                                                                                             |
| 用户管理   | 用户列表、角色修改（防自改）、删除用户（防自删）                                                                                                                                                                                                                                                                     |

### 4.8 个人中心（`/profile`，v1.0.1）

- 顶栏用户头像进入，支持修改邮箱与修改密码（旧密码校验、两次新密码一致校验）

---

## 5. 环境要求

| 组件     | 要求                                                                   |
| -------- | ---------------------------------------------------------------------- |
| Node.js  | **18+**（推荐 20 LTS）                                           |
| npm      | 9+（随 Node 附带）                                                     |
| 后端服务 | `fire_agent_back` 运行于 `http://localhost:8000`（见下方启动说明） |
| 浏览器   | Chrome / Edge 现代浏览器                                               |

---

## 6. 快速启动

### 6.1 启动后端（前置条件）

前端依赖后端 API，请先启动后端服务：

```bash
cd fire_agent_back
conda activate fire_agent_back          # 或你的 Python 环境
uvicorn app.main:app --reload --port 8000
```

后端详细启动步骤见后端仓库 README：https://gitee.com/wjl2004/fire_agent_back

### 6.2 启动前端

```bash
# 1. 进入前端目录
cd fire_agent_front

# 2. 安装依赖（首次）
npm install

# 3. 启动开发服务器
npm run dev
```

启动成功后访问：**http://localhost:5173**

- 默认管理员账号：`admin / 123456`（由后端首次启动时种子创建）
- 未登录会自动跳转到 `/login`

### 6.3 代理配置说明

开发环境由 Vite 代理解决跨域（`vite.config.js`）：

```js
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',   // 后端地址，按需修改
      changeOrigin: true
    }
  }
}
```

若后端不在 8000 端口，修改此处后重启 `npm run dev` 即可。

### 6.4 登录后的默认管理员账号与功能对应关系

| 账号     | 角色  | 可访问页面              |
| -------- | ----- | ----------------------- |
| admin    | admin | 全部 7 页（含系统管理） |
| 注册账号 | user  | 除系统管理外的 6 页     |

---

## 7. 构建与部署

```bash
# 生产构建（输出 dist/）
npm run build

# 本地预览构建产物
npm run preview

# 代码检查
npm run lint
```

生产部署：`npm run build` 后将 `dist/` 目录部署到 Nginx，并将 `/api` 反向代理到后端：

```nginx
server {
    listen 80;
    root /path/to/fire_agent_front/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;   # SPA 路由回退
    }

    location /api {
        proxy_pass http://localhost:8000;   # 后端服务
        proxy_set_header Host $host;
    }
}
```

---

## 8. 常见问题

| 问题                | 解决方案                                                                                                                                |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| 页面空白/数据不显示 | 确认后端已启动（http://localhost:8000/health 返回 ok）；浏览器控制台查看报错；Ctrl+Shift+R 强制刷新清缓存                               |
| 🎤 语音输入无反应   | 确认浏览器麦克风权限已授予（地址栏锁图标 → 麦克风 → 允许）；确认使用 Chrome/Edge 且页面经 localhost 访问（getUserMedia 需安全上下文） |
| 🔊 语音播报失败     | 后端需配置百炼 LLM_API_KEY（TTS 恒定走百炼）；查看后端控制台 TTS 调用报错                                                               |
| 登录后跳回登录页    | 检查后端 JWT_SECRET 配置；清除 localStorage 后重新登录                                                                                  |
| 地图底图不显示      | 天地图 token 失效时更换 token（大屏仍可用本地边界数据渲染）                                                                             |
| 端口被占用          | `npm run dev -- --port 5174` 换端口，同时修改后端 CORS_ORIGINS                                                                        |
| npm install 缓慢    | 使用国内镜像：`npm config set registry https://registry.npmmirror.com`                                                                |

---

## 9. 版本记录

### v1.0.1（当前）

- **Agent 协作中心**：真实 EventSource 消费 SSE 节点级进度（`GET /agent/tasks/{id}/stream?token=`，断线降级拉任务详情）；HITL 审批卡点（报告草稿暂停 → 通过/编辑/驳回 → resume 后定稿落报告中心）；任务历史后端持久化 + 完整回放；`report_delta` 流式报告渲染；新增系统能力面板（`SystemCapabilities.vue`）
- **首页 3D 地图**：新增 `components/Map3D.vue`（Three.js，sc-datav 风格）——州市面片挤出 + 侧面扫光 shader + 贝塞尔飞线 + 旋转光环 + 上升光柱 + CSS2D 标签；火点屏幕空间聚类柱状图（40px 贪心聚类镜像 2D OL Cluster，滚轮 120ms 防抖重建，0 火点州市保留基柱 16 区域全覆盖）；ExtrudeGeometry 实心基座垫块填死边界裂缝；明暗双主题；入场俯冲 2.2s、悬停抬升、`city-click`、`minPolarAngle=0.52`
- **明暗主题系统**：`stores/theme.js` + `style/gis-theme.css` token + `utils/themeTokens.js` 全页面自动适配；玻璃卡化风格 + sc-datav 英文角标（`.datav-en`）
- **全链路语音**：`utils/speech.js`（Web Audio PCM→WAV ASR + TTS 播报）接入大屏 AI 识别/智能查询/知识库/Agent 中心/报告中心
- **报告中心**：类型筛选 + 类型徽标、详细模型名徽标（`llm_model` 优先，回退「阿里百炼/AMD GPU Cloud」）、用户自删/管理员软删
- **知识库**：`/rag/ask/stream` 流式问答 + 非流式兜底
- **智能查询**：查询历史后端持久化（同文本去重）
- **系统管理**：AMD `tokenfactory` 实时模型目录、百炼计费文档实时免费额度目录（5 类）+ 配额快照表、配置保存写 .env 热生效、API Key 脱敏 `sk-***xxx`、系统日志 30s 轮询
- **个人中心**：新增 `/profile`（顶栏头像入口，改邮箱/改密码）
- 配套后端同版本升级：SSE 流式编排、HITL interrupt/resume、Rerank 精排、MCP 天气工具、PostgresStore 记忆、Langfuse 可观测、golden set 评估回归、Docker 交付等

### v1.0.0

初版功能：登录注册 / 2D 作战大屏 / 智能查询 / 知识库 RAG / Agent 协作中心基础版 / 报告中心 / 系统管理基础版。

---

*开发者：wjl（19136220923@163.com） · 前端源码：https://gitee.com/wjl2004/fire_agent_front · 后端源码：https://gitee.com/wjl2004/fire_agent_back*
