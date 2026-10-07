# 前端全站未来感视觉改版计划（含流式验证前置项）

## Context

用户要求：呈现具有未来感的现代化系统前端界面——极简主义布局、高端科技美学、冷色调金属光泽、磨砂玻璃质感、细腻发光线条、深邃专业的数字化氛围、光线柔和漫射、层次感与立体细节、避免杂乱。强调色已确认：**青色/冰蓝（#22d3ee 方向）**，范围：**全站统一改版**。

现状诊断（已通读核实）：
- 主题骨架已存在：`src/style/gis-theme.css`（87 行）定义 `--gis-*` 变量体系 + Element Plus 主色覆盖，加载顺序正确（main.js：common.css → EP CSS → gis-theme.css）
- 三类债务：
  1. EP 变量只覆盖主色 ramp，`--el-color-primary-light-9: #ecfeff` 是**浅色残留 bug**（plain 按钮近白底）；bg/text/border/fill/mask 基础变量全套缺失
  2. 页面渗透不均：dashboard/smart-query/agent-center/knowledge-base 走 `var(--gis-*)`（改值即生效）；**admin（~138 处）、report-center（~73 处）、profile（~23 处）、login（~26 处）为 scoped 硬编码**
  3. 两套青色混用：`rgba(14,165,233,*)`（#0ea5e9）与 `rgba(34,211,238,*)`（#22d3ee）混杂

## 前置项（P0，先于 UI）：流式端到端确诊

上次真 LLM 流式验证出现矛盾证据（`DELTAS=0` 但 `LLMResult len=168`），待确诊：
1. 改进 `scripts/tmp_stream_e2e.py`：worker 记录耗时；主循环改为「worker 存活期间持续消费 + 结束后排空队列（总闸 180s）」，排除 90s 超时窗口造成的假阴性
2. 重跑：若 `DELTAS>1` → 流式链路正常（此前为脚本时序假阴性），删临时脚本收尾
3. 若仍 `DELTAS=0` → 真实投递 bug，按链路排查 `_stream_report → push_delta → loop.call_soon_threadsafe → q`（重点怀疑脚本 loop 绑定与 subscription 竞态）
4. 验证后删除临时脚本；报告/RAG 流式前端已接好（打字机 + fetch reader SSE 解析）

## 改版方案

### 阶段 1：全局 token 层（一切的前提，唯一大改文件）
`src/style/gis-theme.css`（87 → ~300 行）：
- **升级现有变量值**（名称不变，引用处自动渗透）：`--gis-bg-panel` → `rgba(13,22,40,0.82)`、`--gis-bg-panel-2` → `rgba(23,34,56,0.88)`、`--gis-border` → `rgba(70,100,145,0.38)`、`--gis-accent` → `#22d3ee`、`--gis-border-strong` → `rgba(56,189,248,0.8)`、`--gis-grid` → `rgba(103,232,249,0.05)`
- **新增约 28 个变量**（命名延续 `--gis-*`）：
  - 玻璃面：`--gis-glass`(-2/-solid)、`--gis-glass-border`、`--gis-glass-highlight`(inset 顶高光)、`--gis-glass-blur:14px`、`--gis-glass-saturate:140%`
  - 发光线：`--gis-glow`/`--gis-glow-strong`（外发光 box-shadow）、`--gis-line-glow`、`--gis-text-glow`
  - 金属渐变：`--gis-metal-accent`（青色 145deg 渐变，主按钮/徽标/头像）、`--gis-metal-sheen`（顶部扫光）、`--gis-metal-edge`（顶边亮线）、`--gis-metal-text`（background-clip:text 金属字）
  - 氛围光晕：`--gis-halo-a/b/c`（三组低透明度大半径径向光晕）+ 合成值 `--gis-atmo-bg`
  - 圆角/间距尺度：`--gis-radius-xs/sm/md/lg`、`--gis-space-xs/sm/md/lg`
- **EP 深色缺口补齐**：① bg/text/border/fill/mask/disabled 基础变量全套（input/table/dialog/pagination 等自动适配）；② 修复主色 ramp（light-9 由 `#ecfeff` → `rgba(34,211,238,0.12)`）；③ success/warning/danger/info 四组深色 ramp（light-7/8/9 用 rgba 透明化，否则 el-tag plain 刺眼浅底）；④ 组件级：`.el-table` 变量组、`.el-dialog`/MessageBox 玻璃底、日期弹层选择器扩展
- **全局基础设施**：`.gis-glass`/`.gis-metal-text` 工具类、`a { color: var(--gis-accent) }`（覆盖 common.css L135-140 暗蓝残留）、`::selection`、全局细滚动条

### 阶段 2：MainLayout（`src/layout/MainLayout.vue` 样式段 L74-219）
- `.app-shell` 背景 → `var(--gis-atmo-bg)`（**全站氛围层入口**）
- `.app-sidebar`：玻璃底 + blur + 右缘发光线；`.nav-item` active 左侧 2px 金属发光条 + `--gis-glow-strong`；`.user-avatar` → 金属渐变

### 阶段 3：login（玻璃样板间，`src/views/login/index.vue` L146-302）
- 背景 → `--gis-atmo-bg`；`.login-card` → `--gis-glass` + blur(18px) + 玻璃边 + 顶部金属扫光；输入框 focus 发光；`.submit-btn` → 金属渐变

### 阶段 4：dashboard（`src/views/dashboard/index.vue` L1133-1989，只改 chrome）
- 壳层 → atmo-bg；顶栏玻璃化；logo 徽标金属渐变；`.gis-panel` 玻璃边 + inset 高光；`.gis-map-frame` 发光外框（**内部 `#000` 与天地图画布不动**）
- 地图上两个浮层（`.fire-warning-detail` L1385-1401、`.weather-popup` L1846-1857）→ `--gis-glass-solid` + blur，保证压瓦片可读
- **火险预警红/黄语义色、风险 5 档色板一律不动**

### 阶段 5-9：其余页面（变量渗透为主 + 硬编码清理）
统一动作：壳层一行换 `var(--gis-atmo-bg)`；主面板换玻璃三件套；`rgba(14,165,233,*)` 全部归一到 `rgba(34,211,238,*)`/`var(--gis-accent-dim)`；主按钮 → `var(--gis-metal-accent)`
- smart-query（L678+）、agent-center（L727+）、knowledge-base（L523+）：改动量最小（变量已渗透）
- report-center（L361+）：73 处硬编码替换（`#0a0f1e`/`#0b1120`/`#1e293b`/`#172033` hover）
- admin（L1329+，重灾区）：tab 栏玻璃 pill、10 处 `#0f172a` → `var(--gis-bg-panel)`、实心 `#0ea5e9` → `var(--gis-accent)`、虚线框归一
- profile（L183+）：壳层 + 卡片玻璃三件套
- chart 组件 4 个文件：**跳过 ECharts option 内色值**，仅对齐 expand/maximize 容器件

### 氛围层与性能红线
- 光晕封装进 `--gis-atmo-bg`，逐页壳层一行替换（共 8 处壳层）；**不铺 body/#app 全局底**——光晕永远被面板与地图画布压在下层，物理上不会渗进地图
- `backdrop-filter` 仅限：侧栏、dashboard 顶栏、两个地图浮层、登录卡；大面积面板用半透明色（无 blur），禁止套在滚动容器上

## 关键文件
- `src/style/gis-theme.css`（token 层，一切前提）
- `src/layout/MainLayout.vue`、`src/views/login/index.vue`、`src/views/dashboard/index.vue`
- `src/views/{smart-query,agent-center,knowledge-base,report-center,admin,profile}/index.vue`
- `scripts/tmp_stream_e2e.py`（后端临时验证脚本，用后删）

## 验证
1. **流式**（前置项）：`python -u scripts\tmp_stream_e2e.py`（conda 或系统 Python 均可，LLM 走 amd）断言 `DELTAS>1`
2. **构建**：`cd e:\Yunnan_fire_agent\fire_agent_front` → `node node_modules\vite\bin\vite.js build`（禁用 npx）
3. **人工检查清单**（构建通过后交用户目验）：
   - 风险 5 档色板与 `utils/riskLevel.js` 一致；地图/ECharts 本体零变化
   - EP 组件深色无白底块（重点：dialog/select 下拉/date-picker/table/message/pagination）
   - 地图浮层压瓦片可读；两套青色归一（全局搜 `rgba(14, 165` 清零）
   - 登录双模式布局不破；链接/选中态为冰青色；dashboard 拖图不掉帧（blur 未滥用）
   - 各页展开面板（agent-center 260px / report-center 340px / kb 280px）无溢出破版
