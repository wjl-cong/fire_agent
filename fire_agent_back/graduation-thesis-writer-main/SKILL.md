---
name: graduation-thesis-writer
description: Write, polish, audit, and diagram high-quality Markdown-only Chinese undergraduate graduation theses from project code, database schemas, APIs, screenshots, PDFs, and user notes. Use when the user asks to audit materials, learn from reference thesis templates, create a thesis outline, draft chapters, prepare PlantUML MCP or draw.io diagrams, improve Chinese academic expression, remove AI-sounding Word-style text, generate figure/table captions, prepare references, testing sections, reviewer-style checks, or Word-convertible Markdown thesis text for software, AI, large-model, web, mobile, or data-system projects.
---

# Graduation Thesis Writer

## Purpose

Use this skill to produce a rigorous, code-faithful Chinese undergraduate graduation thesis as a single high-quality Markdown document that can later be converted to Word. Treat the implemented project as the source of truth, and use reference PDFs, Word templates, school examples, and excellent thesis samples to learn structure, academic tone, formatting patterns, chapter depth, and figure/table habits.

Do not generate `.docx` by default. Produce Markdown as the primary and final artifact unless the user explicitly asks for another format.

## Source Priority

Follow this order when deciding what may be stated as fact:

1. Source code, database models, migrations, SQL scripts, tests, and runtime behavior.
2. Configuration files, dependencies, API definitions, prompts, deployment scripts, and logs.
3. README files, design documents, comments, screenshots, and generated artifacts.
4. Explicit user-provided explanations.
5. Reference PDFs, Word templates, school examples, and excellent thesis samples for chapter structure, paragraph organization, style, and formatting habits only.

When evidence is missing, write "待补充信息" or "此处需用户补充..." instead of inventing features, metrics, experiments, references, or conclusions.

## Required Workflow

### 1. Audit Materials First

Before drafting the thesis body, inspect available code and materials. Identify:

- Project type and thesis topic.
- Frontend, backend, database, AI/model, deployment, and third-party service stack.
- Core modules, classes, functions, APIs, schemas, tables, prompts, and workflows.
- Screenshots, PDFs, reports, logs, and test data that can support thesis figures or results.
- Missing evidence and which chapters it affects.

If the materials are insufficient for a full thesis, output a "材料审计与缺口报告" and limit drafting to safe chapters.

For deeper workflow details, read `references/workflow.md`.

### 2. Learn From Reference Templates

Before producing the final outline, extract reusable writing and formatting patterns from the user's reference templates:

- Chapter sequence and naming conventions.
- Abstract length, keyword style, and bilingual abstract pattern.
- Depth of literature review and related-technology explanation.
- Figure/table numbering style, caption style, and placement habits.
- Requirement-analysis, database-design, implementation, and testing-section organization.
- School-specific formatting constraints, if a template is provided.

Never copy project facts, experimental results, references, business modules, or algorithm claims from a template unless the user's own project materials support them.

For detailed template-learning rules, read `references/template-learning.md`.

### 3. Build a Four-Level Outline

After the audit, output a detailed outline before writing chapters. The outline must:

- Include headings down to four levels where useful.
- Tie every major section to verified project implementation.
- Add a short "拟写内容" note after second- or third-level headings.
- Mark required figures, tables, formulas, screenshots, sequence diagrams, E-R diagrams, architecture diagrams, and flowcharts.
- Mark unsupported parts as "待补充".

Wait for user confirmation before drafting chapters unless the user explicitly asks to continue without confirmation.

### 4. Draft Chapter by Chapter

For each chapter:

- Start with the chapter writing goal.
- Write formal, objective academic Chinese.
- Convert code facts into academic prose instead of copying code.
- Insert figure/table placeholders where appropriate.
- Use a PlantUML-MCP-first strategy for software-engineering UML figures when the user requests UML quality, PlantUML, or the PlantUML MCP server. For UML use-case/activity/sequence/class/state/component/deployment diagrams, PlantUML usually gives more consistent academic linework than hand-made draw.io sources. Generate `.puml` source plus rendered `.png` and `.svg` artifacts, embed PNG in the Markdown body for Word conversion, and keep SVG as a vector backup.
- Use draw.io/diagrams.net when the user explicitly asks for draw.io, when a diagram needs manual layout that PlantUML cannot express well, or when a polished architecture poster-style diagram is more appropriate than strict UML. For architecture diagrams, DFDs, E-R diagrams, module diagrams, business workflows, deployment diagrams, and algorithm workflows, the final Markdown should point to a durable `.puml`, `.png`, `.svg`, or `.drawio` artifact. For a Word-convertible final thesis, do not leave structural figures as raw Mermaid code blocks in the body.
- When PlantUML MCP is available, use `generate_plantuml_diagram` to render SVG/PNG and save them locally. The known server at `https://mcpservers.org/servers/github-com-infobip-plantuml-mcp-server` exposes `generate_plantuml_diagram`, `encode_plantuml`, and `decode_plantuml`; it supports `PLANTUML_SERVER_URL` and `PLANTUML_ALLOWED_DIRS` for local output control. If the MCP is unavailable but Node/npm is available, `npx -y plantuml-mcp-server` may be used as a stdio MCP server after confirming permissions.
- When draw.io MCP is available and is the chosen path, use it to create polished diagrams. When no draw.io MCP tool is callable, create diagrams.net-compatible `.drawio` XML files in the project, for example `docs/drawio/Figure-X.drawio`, and reference them from the figure placeholder. Mermaid may be used only as a private drafting aid or for quick analysis, not as the final visible thesis diagram format unless the user explicitly requests Mermaid.
- If the user asks to improve figure quality or says Mermaid diagrams are ugly/too tall, convert every structural figure in the relevant chapters to PlantUML MCP or draw.io sources. Prefer PlantUML MCP for strict UML diagrams such as use-case, activity, sequence, state, class, component, and deployment diagrams; prefer draw.io only for manually composed architecture/data-flow diagrams where PlantUML layout is unsuitable. Keep screenshot figures as screenshot placeholders rather than generated diagram files.
- Keep diagrams Word-page friendly: prefer horizontal swimlanes, staged matrices, two-row pipelines, compact component groups, and split subfigures over tall vertical chains. Avoid `mindmap` Mermaid for thesis deliverables because it is less stable across renderers.
- Every figure, exported diagram, screenshot placeholder, and image must have a visible caption using the thesis template style, plus an insertion placeholder that states the source file or required screenshot.
- Apply conservative Chinese academic polishing: fix口语化、语病、逻辑断层、翻译腔和明显 AI 味, but do not rewrite already clear paragraphs just to sound more "advanced". Prefer plain, accurate, modern academic Chinese over ornate or old-fashioned wording.
- Generate concise figure and table titles. Captions should directly identify the object and purpose, avoid empty phrases such as "展示了", "可以看出", or promotional wording, and keep numbering consistent with the chapter.
- Keep claims proportional to evidence.

For algorithm or AI-agent sections, include:

- Design motivation.
- Principle and workflow.
- Key formulas only when they reflect real logic.
- Mapping between implementation and thesis description.

For system implementation sections, include:

- Module responsibilities.
- Key classes, APIs, data structures, and interactions.
- Data flow and error handling.
- Screenshot placeholders.

### 5. Handle References Carefully

Never fabricate references. Use only real, verifiable sources from authoritative venues or official documentation. If citations have not been verified, create a "待核验参考文献位" list instead of a fake bibliography.

### 6. Final Consistency Check

Before final delivery, check:

- Terms, module names, and technology names are consistent.
- Functions and tables match the code.
- Diagrams match real architecture.
- Test results come from real evidence.
- No unsupported performance numbers, experiment conclusions, or invented modules remain.
- Reviewer-style risk pass: identify fatal or material issues first, including unsupported claims, weak evidence, inconsistent contribution statements, missing tests, unclear diagrams, or AI-sounding prose. Ignore purely cosmetic changes unless they affect Word conversion or academic readability.

Use `references/quality-checklist.md` before final thesis assembly.

For Markdown deliverable standards, read `references/markdown-output.md`. For diagram strategy, read `references/diagramming.md`. For Chinese polishing, AI-tone removal, captions, and reviewer-style language checks, read `references/writing-polish.md`.

## Default Thesis Shape

Adapt the structure to the project, but prefer:

1. 摘要
2. Abstract
3. 第1章 绪论
4. 第2章 相关技术与理论基础
5. 第3章 需求分析
6. 第4章 系统总体设计
7. 第5章 核心算法与关键技术实现
8. 第6章 系统实现
9. 第7章 系统测试与结果分析
10. 第8章 总结与展望
11. 参考文献
12. 附录

If the project has no self-trained model or experimental algorithm, do not force a deep-learning experiment chapter. Rename the chapter to "核心流程与关键技术实现" or another code-faithful title.

## Output Contract

The final artifact should be one Markdown file in the user's target project directory. It should be directly convertible to Word after:

- Replacing diagram placeholders with exported PlantUML PNG/SVG or draw.io images first; use Mermaid-exported images only for simple fallback diagrams.
- Replacing screenshot placeholders with real screenshots.
- Applying the school's Word style template.

Do not make the final body depend on raw Mermaid code blocks for major diagrams. If a diagram is visually important, long, renderer-sensitive, or likely to occupy too much vertical space, provide a PlantUML `.puml` source plus exported image path, or a draw.io source file and write the body as a formal figure placeholder with a caption.

Do not auto-export Word, PDF, or other formats unless the user explicitly requests it.

## Teacher-Review Hard Rules: Chinese Software Graduation Thesis

When rewriting or generating a Chinese undergraduate software-engineering thesis after teacher review, apply these rules as hard constraints before style polish.

### Abstract and Keywords
- The abstract must show real workload: problem background, adopted method, completed system work, validation method, and conclusion boundary.
- Do not make the abstract read like "called an API and built a page"; emphasize method and engineering process, not a pile of frameworks.
- Keep Chinese keywords to five or fewer.

### Chapter Logic
- Use an 8-chapter structure when the advisor asks for it: Introduction, Related Technology, Feasibility Analysis, Requirement Analysis, System Design, System Implementation, System Testing, Summary.
- Split research status into foreign research and domestic research.
- Keep design and implementation separate: design chapters explain structure and rationale; implementation chapters explain code-level realization and data flow.
- Do not write two consecutive chapters that are both essentially implementation.
- Remove low-value standalone login tests unless the system contribution is authentication itself.

### Source-Code Abstraction
- Do not put source file names, low-level type names, or implementation nodes into the thesis body. Use abstract Chinese semantic names such as "会话应用服务", "智能编排组件", "路线生成工具".
- If code-to-thesis mapping is useful, place it in an appendix table only.
- Avoid phrases such as "根据项目实现", "该图有助于解释", "主要实现以下能力", "本文围绕……展开" in final thesis prose.

### Figures and Tables
- Every figure must have an introduction before it: use wording equivalent to "如图 X-X 所示" and explain why the figure appears.
- Every figure must have a caption immediately after the image or placeholder.
- Every table must have a table title and explanatory text before or after the table; never leave a heading followed only by a table.
- For software-engineering UML figures, prefer PlantUML MCP or PlantUML-style sources. Use abstract Chinese labels, avoid source filenames, long node sentences, crossed edges, unexplained multiplicity marks, and oversized vertical chains.

### References and Citations
- Main references should be academic papers from CNKI, Wanfang, journal sites, IEEE, ACM, Elsevier, Springer, or arXiv papers with scholarly visibility.
- Do not count official docs, framework manuals, platform pages, or project READMEs as main thesis references.
- For typical Chinese undergraduate theses, prepare at least 30 academic references, with at least 10 Chinese references when the advisor requests it.
- English literature should be discussed in Chinese in the body, while the reference list keeps the original English title.

### Testing Chapter
- Use black-box functional testing, exception testing, interface/screenshot verification, and performance test plans.
- Do not fabricate response time, throughput, accuracy, or concurrency metrics without logs.
- In final thesis prose, never expose audit phrases such as "材料未提供", "无依据结论", "待记录指标", "未形成压测报告", or "需在答辩前补充". Material gaps belong in an audit report, not in the deliverable thesis body. If metrics are unavailable, write a formal qualitative test result or test method without revealing the gap.

- Final thesis body must not contain audit notes about unavailable screenshots, unavailable logs, missing materials, or lack of pressure-test data. Keep those notes outside the thesis or in a private delivery checklist.

## Citation Order Rule

For Chinese undergraduate theses that use numeric references, enforce sequential citation order:

- Number references by first appearance in the thesis body, not by language category, topic, or alphabetic order.
- If foreign research appears before domestic research, the foreign papers cited there must receive the earliest numbers.
- Later chapters may reuse earlier numbers; repeated citations do not need to be monotonic.
- Before delivery, scan the body before the reference list, ignore code blocks, expand ranges such as [18-21], and confirm first occurrence is [1], [2], [3] ... without jumps.
- Keep uncited but retained background papers after the cited references, continuing the numbering sequence.

## Academic Abstraction Rule

For "design and implementation" undergraduate theses, do not let the paper read like a project introduction, product manual, or feature list.

- Start from the research problem, task abstraction, constraints, design principles, mechanism model, and verification logic.
- Replace product-manual wording such as "用户可以", "系统提供", "页面展示", "功能包括" with academic wording such as "任务链路", "状态转换", "职责边界", "约束建模", "机制设计", "验证维度".
- Requirements chapters should analyze input characteristics, state characteristics, output characteristics, role boundaries, and constraint conditions, not merely list operations.
- Design chapters should explain why a structure is chosen: generation/execution separation, state-driven orchestration, traceable data, maintainable boundaries, security constraints.
- Implementation chapters may mention concrete modules, but each module must be tied to a mechanism: event stream, data transformation, consistency, fallback, persistence, or permission boundary.
- Testing chapters should verify design claims and task-state transitions, not read like a user acceptance checklist.
- Keep necessary software-engineering terms such as function, module, page, and interface only when they are part of formal analysis; avoid piling them into descriptive feature lists.

## Reference DOCX Structure and Black-White UML Rule

When a user provides a reference thesis in DOCX form, extract style patterns rather than project facts:

- Learn chapter organization, heading depth, chapter-summary placement, figure/table density, caption style, and testing-section layout.
- Do not copy the reference project domain, modules, data, results, or references into the target thesis.
- For traditional software-engineering theses, prefer adding chapter summaries such as "本章总结" and a "论文结构" section when the reference template uses them.
- Requirement analysis should contain dense but relevant software-engineering diagrams: use-case, sequence, activity, state, class/interface or data-analysis diagrams as appropriate.
- Design chapters should follow the common order: architecture, function/module structure, database design, component/field/object design, deployment or navigation design.
- For UML and software-engineering diagrams intended for Word, default to black-white professional line art: white background, black borders, black arrows, no gradient, no pastel module fills, no decorative icons, and compact A4-friendly layout.
- Keep color only when the user or school template explicitly requires it; otherwise black-white diagrams are safer for printing, review, and thesis formatting.
