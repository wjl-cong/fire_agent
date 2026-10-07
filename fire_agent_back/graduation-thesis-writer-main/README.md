# Graduation Thesis Writer

`graduation-thesis-writer` 是一个面向 Codex 的中文本科毕业设计论文写作 skill。它用于从真实项目代码、数据库结构、接口实现、系统截图、测试材料和参考论文模板中提炼事实，生成一篇可直接整理为 Word 的高质量 Markdown 毕业论文。

本 skill 的核心目标不是“套模板凑字数”，而是让论文尽可能接近真实优秀毕设的写法：先审计材料，再建立论文结构，再逐章写作，并为系统架构、需求分析、UML 图、数据库设计、系统测试截图等内容预留可交付的位置。

## 适用场景

- 软件系统类毕业设计：管理系统、推荐系统、智能助手、可视化平台、移动端应用、Web 应用等。
- AI 与大模型应用类毕业设计：多 Agent 系统、RAG 应用、智能问答、工具调用、智能规划、图像识别、NLP 应用等。
- 需要参考优秀论文或学校模板，输出 Markdown 后再转换为 Word 的论文写作任务。
- 需要将项目代码、数据库、接口、截图、测试结果和参考文献统一整理成正式论文文本的任务。

## 核心能力

- 材料审计：先检查代码、数据库、接口、配置、README、截图、PDF、测试数据是否足以支撑完整论文。
- 代码优先：以真实源代码和数据库结构为事实依据，避免把参考论文中的功能硬套到当前项目。
- Markdown 成稿：默认输出单篇高质量 Markdown 文件，便于后续用 Pandoc、Typora、WPS、Word 插件或学校模板转换为 Word。
- draw.io 图优先：正式结构图优先使用 draw.io / diagrams.net 源文件或导出图，避免把复杂 UML 图直接留成单调 Mermaid。
- UML 与系统图支持：支持用例图、活动图、时序图、类图、E-R 图、部署图、模块图、数据流图、业务流程图和算法流程图。
- 图文并茂：为系统运行界面、测试结果、部署截图、模型/算法流程等位置生成规范截图占位和题注。
- 表格规范：生成数据库表结构、接口设计表、功能测试用例表、非功能需求表、参考文献表述等论文常见表格。
- 表达润色：使用正式、自然、现代的学术中文，减少口语化、翻译腔和明显 AI 味。
- Reviewer 视角检查：最终检查真实性、结构、图表、测试证据、术语一致性、参考文献和过度结论。

## 安装方式

将本仓库克隆到 Codex skills 目录：

```powershell
git clone https://github.com/Mengsanfen/graduation-thesis-writer.git "$env:USERPROFILE\.codex\skills\graduation-thesis-writer"
```

如果已经存在同名目录，可以先备份旧版本，再重新克隆或拉取更新：

```powershell
cd "$env:USERPROFILE\.codex\skills\graduation-thesis-writer"
git pull
```

macOS / Linux 可使用：

```bash
git clone https://github.com/Mengsanfen/graduation-thesis-writer.git ~/.codex/skills/graduation-thesis-writer
```

安装后，在 Codex 中直接使用 `$graduation-thesis-writer` 调用。

## 推荐准备材料

材料越完整，论文越真实、越像可交付成稿。以下材料不是全部必需，但建议尽量提供。

| 材料类型 | 是否必需 | 用途 |
| --- | --- | --- |
| 项目源代码 | 强烈建议 | 确认技术栈、模块划分、接口、数据库、核心流程 |
| 数据库脚本或 ORM 模型 | 强烈建议 | 撰写数据库设计、E-R 图、表结构说明 |
| README / 开发文档 | 建议 | 辅助理解项目背景、运行方式和功能边界 |
| 接口文档 / Swagger / Postman | 建议 | 撰写接口设计、时序图、测试用例 |
| 参考论文 PDF / 学校模板 | 可选但推荐 | 学习章节结构、题注格式、图表密度和论文风格 |
| 系统界面截图 | 推荐 | 支撑系统实现章节和系统测试章节 |
| 测试截图 / 日志 / 测试数据 | 推荐 | 支撑测试结果，避免虚构性能或功能结论 |
| 部署截图 / 配置说明 | 可选 | 支撑部署架构图和运行环境说明 |
| 参考文献线索 | 可选 | 辅助生成真实、可检索的中英文参考文献 |

## 推荐材料目录

可以在项目中按如下方式整理材料，便于 skill 审计：

```text
your-project/
├── frontend/
├── backend/
├── docs/
│   ├── reference/
│   │   └── 论文参考.pdf
│   ├── screenshots/
│   │   ├── 登录页.png
│   │   ├── 首页.png
│   │   ├── 核心功能页.png
│   │   └── 测试结果.png
│   ├── api/
│   │   └── 接口说明.md
│   └── testing/
│       └── 测试记录.md
├── database/
│   └── schema.sql
└── README.md
```

也可以不整理目录，直接在对话中说明文件路径。skill 会优先读取真实代码和材料。

## 基本使用方式

### 1. 先做材料审计和大纲

```text
$graduation-thesis-writer
请先审计当前项目代码和我提供的参考论文，输出《材料审计与项目认知摘要》，再输出详细到四级标题的毕业设计论文大纲。论文题目为《基于多Agent智能旅行助手的设计与实现》。
```

适合首次写论文时使用。skill 会先判断材料是否充分，不会在证据不足时直接虚构完整论文。

### 2. 根据确认后的大纲逐章写作

```text
$graduation-thesis-writer
我确认该大纲。请先撰写第 1 章和第 2 章，要求符合本科毕业论文风格，保留图表和参考文献待补充位置。
```

适合分阶段生成正文，便于逐章检查和修改。

### 3. 直接生成 Markdown 成稿

```text
$graduation-thesis-writer
请基于当前项目直接生成完整 Markdown 毕业论文，输出到项目根目录。要求包含摘要、Abstract、绪论、相关技术、需求分析、总体设计、关键技术实现、系统实现、系统测试、总结与展望、参考文献和附录。
```

如果材料不足，skill 会把无法支撑的内容标记为“待补充信息”，而不是编造。

### 4. 优化现有论文

```text
$graduation-thesis-writer
请审查并优化当前项目中的毕业论文 Markdown，重点检查：是否与代码一致、图表是否缺少题注、是否存在 AI 味表达、测试章节是否缺少截图占位、参考文献是否真实可核验。
```

适合已有初稿后的质量提升。

### 5. 强化图表和 UML

```text
$graduation-thesis-writer
请把论文中的结构图全部改为 draw.io 风格，需求分析章节补充用例图、活动图和业务流程图，系统设计章节补充架构图、模块图、E-R 图和时序图。图要适合 A4 Word 页面排版。
```

如果可用 draw.io MCP，skill 会优先使用 MCP；如果不可用，会生成 diagrams.net 兼容的 `.drawio` 源文件，并在 Markdown 中插入规范占位。

## 截图占位写法

对于系统运行界面和测试结果，skill 不会虚构截图，而是生成清晰的占位说明。例如：

```text
图 7-1 系统登录页
[此处插入：图 7-1 系统登录页 - 展示用户身份认证界面]

图 8-2 智能旅行规划功能测试结果
[此处插入：图 8-2 智能旅行规划功能测试结果 - 展示输入旅行需求后系统生成行程方案的测试结果]
```

你可以后续将真实截图插入 Word，并保留这些题注。

## 图表规范

skill 默认遵循以下图表规则：

- 所有图、截图、导出图和表格都必须有题注。
- 图题采用 `图 章节号-序号 图名`，如 `图 5-1 系统总体架构图`。
- 表题采用 `表 章节号-序号 表名`，如 `表 4-2 用户表结构`。
- UML 图和架构图应简洁、白底、短标签、适合 A4 页面。
- 长流程图优先拆分为泳道图、阶段矩阵、双行管线图或多个子图。
- 不把复杂 Mermaid 代码块作为正式论文最终图。

## 真实性约束

为了保证论文可答辩、可审查，skill 会遵守以下原则：

- 代码和数据库优先于参考论文。
- 未在代码、文档、截图、日志或用户说明中出现的功能，不写成“已实现”。
- 没有真实测试数据时，不编造性能指标。
- 没有真实文献来源时，不伪造参考文献。
- 缺失材料会明确标注为“待补充信息”或“此处需用户补充...”。
- 参考论文只用于学习结构、表达和排版，不复制其项目事实。

## 输出结果

默认输出包括：

- 材料审计与缺口报告。
- 项目认知摘要。
- 四级标题论文大纲。
- Markdown 正文成稿。
- draw.io 图源文件或图表占位。
- 系统截图与测试截图占位。
- 参考文献或待核验参考文献位。
- 最终一致性检查报告。

默认不输出 `.docx`。如果需要 Word，可先将 Markdown 转为 Word，再套用学校模板。

## 仓库结构

```text
graduation-thesis-writer/
├── SKILL.md
├── README.md
├── agents/
│   └── openai.yaml
└── references/
    ├── diagramming.md
    ├── markdown-output.md
    ├── quality-checklist.md
    ├── template-learning.md
    ├── workflow.md
    └── writing-polish.md
```

## 适合配合使用的外部工具

- draw.io / diagrams.net：编辑和导出论文结构图。
- drawio-mcp：让 Codex 通过 MCP 生成或维护 draw.io 图。
- Pandoc：将 Markdown 转换为 Word。
- Typora / MarkText / VS Code：预览和整理 Markdown。
- WPS / Microsoft Word：套用学校模板、插入截图、更新目录和页码。

## 注意事项

- 本 skill 不能替代真实项目实现，也不会自动生成不存在的功能。
- 如果项目代码缺失、截图缺失或测试数据不足，论文会保留待补充标记。
- 若学校模板对标题、页眉页脚、目录、题注、参考文献格式有特殊要求，应以学校模板为最终排版依据。
- 使用大模型或 AI Agent 相关主题时，应说明真实调用链、工具能力和系统边界，避免用空泛概念替代实现细节。

## PlantUML MCP for Software Engineering UML

Starting with this version, strict software-engineering UML diagrams should prefer PlantUML MCP instead of forcing every figure into draw.io. Use-case, activity, sequence, class, state, component, and deployment diagrams benefit from stable syntax, uniform linework, reproducible rendering, and source-controlled `.puml` files.

- MCP server: <https://mcpservers.org/servers/github-com-infobip-plantuml-mcp-server>
- Main tools: `generate_plantuml_diagram`, `encode_plantuml`, `decode_plantuml`
- Recommended outputs: keep `.puml` source, `.png` image for Markdown/Word conversion, and `.svg` vector backup
- Recommended directories: `thesis/plantuml/` or `docs/figures/plantuml/`
- Word conversion advice: embed PNG in Markdown first, then replace with SVG or re-export from PlantUML when the final Word document needs sharper vector graphics

Optional MCP startup when the local client and npm/network permissions allow it:

```bash
npx -y plantuml-mcp-server
```

Common environment variables:

```text
PLANTUML_SERVER_URL=https://www.plantuml.com/plantuml
PLANTUML_ALLOWED_DIRS=/absolute/path/to/project
```

Example prompt:

```text
$graduation-thesis-writer
Please rebuild all software-engineering UML figures in the thesis with PlantUML MCP, including `.puml` source files, PNG images, and SVG backups. In the requirement-analysis chapters, prioritize use-case, activity, and sequence diagrams. In the system-design chapters, prioritize class, component, deployment, and E-R diagrams. All diagrams must fit A4 Word pages and include captions.
```

draw.io remains useful for hand-polished architecture diagrams, data-flow diagrams, module overviews, and page-navigation diagrams. When the user explicitly requests draw.io or the figure needs complex manual layout, this skill may still use draw.io/diagrams.net.

## Advisor-Review Usage Notes

For teacher-reviewed Chinese software theses, run the skill in this order:

1. Audit the project code, database models, screenshots and reference thesis.
2. Rewrite the abstract first, showing real workload rather than framework names.
3. Rebuild the outline into clear analysis, design, implementation and testing chapters.
4. Recreate UML figures with PlantUML-style sources and abstract Chinese labels.
5. Add screenshot placeholders in the testing chapter for each user-visible core function.
6. Rebuild references from academic papers; keep policies and laws separate if they are background evidence.
7. Run the advisor-review gate in references/quality-checklist.md before delivery.
