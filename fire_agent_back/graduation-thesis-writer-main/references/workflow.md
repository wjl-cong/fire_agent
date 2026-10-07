# Graduation Thesis Workflow

## Material Audit Output

Produce these sections after reading materials:

- 已识别材料清单
- 已确认技术栈
- 已确认核心功能/算法/模块
- 数据库与接口事实
- 截图、PDF、测试材料可用性
- 缺失材料清单
- 缺失内容影响的论文章节
- 当前可安全撰写范围
- 项目认知摘要

## Code Audit Checklist

Inspect, when present:

- Dependency files: `package.json`, `pyproject.toml`, `requirements.txt`, `pom.xml`, `build.gradle`, lockfiles.
- Entry points: app bootstrap files, routers, controllers, server startup, frontend main files.
- Models and database: ORM models, SQL scripts, migrations, entity relationships.
- API layer: route paths, methods, request schemas, response schemas, auth handling.
- AI/model layer: prompts, graph/workflow files, tool registry, inference code, checkpoint logic.
- Services: business logic, PDF/export, file upload, external API clients, error handling.
- Frontend: pages, components, stores, API clients, conditional compilation, static assets.
- Tests and evidence: unit tests, integration tests, screenshots, generated files, logs.

## Reference PDF Use

Use reference PDFs and Word templates to learn:

- Chapter ordering.
- Academic tone.
- Density of technical explanation.
- Figure/table placement.
- Test case layout.
- Abstract style.
- School-specific formatting requirements.
- Excellent-thesis paragraph organization.

Do not copy project facts, algorithm claims, performance results, references, or domain modules from reference PDFs unless they also exist in the user's project.

When the user provides reference templates, read `template-learning.md` and include "参考模板学习结果" in the material audit.

## Diagram Requirements

Prefer draw.io MCP for polished thesis diagrams when a draw.io MCP server/tool is available. The draw.io MCP repository describes several integration approaches, including an MCP App Server that can render diagrams inline and a tool server that can open diagrams in draw.io; it supports XML, CSV, and Mermaid in the tool-server path. Use this capability when available for final-quality diagrams.

Use diagrams for:

- System architecture diagram.
- Functional module diagram.
- Core workflow diagram.
- Sequence diagram for login/chat/export.
- E-R diagram from real database models.
- Deployment diagram if deployment files or user notes support it.
- Class diagram or package diagram when code entities are central.
- Activity diagram when the reference template emphasizes behavior analysis.

For every diagram:

1. Prefer creating or specifying a draw.io diagram via MCP when available.
2. Include the diagram source or a durable pointer to the generated `.drawio`/exported image.
3. Add one sentence explaining the diagram.
4. Insert a placeholder such as `[此处插入：图4.1 系统总体架构图 - 展示前端、后端、智能体工具与数据库之间的关系]`.
5. If draw.io MCP is unavailable, create or reference a diagrams.net-compatible `.drawio` XML source file. Use Mermaid only as a private drafting aid or when the user explicitly requests Mermaid output.

Read `diagramming.md` before producing diagrams in the final thesis.

## Screenshot Placeholder Pattern

Use precise placeholders:

- `图 7-1 系统登录页`
  `[此处插入：图 7-1 系统登录页 - 展示用户身份认证界面]`
- `图 7-2 智能对话页`
  `[此处插入：图 7-2 智能对话页 - 展示流式回复与工具调用状态]`
- `图 7-3 地图路线展示页`
  `[此处插入：图 7-3 地图路线展示页 - 展示按天生成的出行路线]`
- `图 7-4 行程档案页`
  `[此处插入：图 7-4 行程档案页 - 展示PDF收藏、备注与删除功能]`
- `图 8-1 功能测试结果`
  `[此处插入：图 8-1 功能测试结果 - 展示接口或页面测试通过情况]`

## Writing Rules

- Use formal academic Chinese.
- Apply conservative polishing and remove obvious AI-sounding filler according to `writing-polish.md`.
- Explain why a design is used, not only what was built.
- State "依据代码可知..." only when helpful; usually write naturally.
- Avoid marketing language and unverifiable adjectives.
- Avoid formulas when there is no real mathematical process in the implementation.
- Mark missing performance data, test data, and citation sources explicitly.

## Final File Rule

Write the final thesis as a Markdown file in the project directory. Do not generate Word by default. The Markdown must be structured enough to convert directly to Word later.
