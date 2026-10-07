# Chinese Thesis Writing Polish

Use this reference when polishing Chinese undergraduate theses, removing AI-sounding prose, generating figure/table captions, or doing a reviewer-style final pass. Keep the thesis grounded in code and evidence; style improvements must not introduce unsupported facts.

## Conservative Polishing

- Preserve good text. If a paragraph is already clear, accurate, and academic, keep it rather than rewriting for variety.
- Fix only meaningful issues:口语化表达、语病、指代不明、逻辑断层、严重欧化长句、术语前后不一致、格式不适合 Word.
- Prefer modern academic Chinese: plain, precise, and natural. Do not force old-style wording such as "系", "拟", "诚然", or excessive "旨在" unless the surrounding style requires it.
- Keep one paragraph focused on one core idea. If a paragraph mixes background, method, result, and limitation, split or reorder it.
- Use semantic transitions instead of mechanical connectors. Avoid stacking "首先、其次、最后" unless listing steps or test cases is genuinely clearer.

## Remove AI-Sounding Chinese

Replace empty or promotional language with concrete academic description:

- "为了解决这一痛点" -> "针对上述问题"
- "展现了令人惊叹的能力" -> "表现出较强的任务处理能力" or a measured, evidence-backed result
- "深刻揭示了", "不可磨灭的贡献", "范式转移", "颠覆性", "切中要害", "本质上" -> use the specific mechanism, evidence, or limitation instead.

Style rules:

- Avoid long English-style modifiers such as "一个...的...的系统". Split into shorter clauses.
- Avoid unnecessary passive "被" constructions. Prefer "系统采用...", "本文设计...", "实验结果表明...".
- Do not replace technical terms just to sound less AI-generated. Preserve names such as LangGraph, MCP, WebSocket, SQLModel, PostgreSQL, UniApp.
- Do not over-polish evidence markers. If information is missing, keep "待补充信息" or "此处需用户补充..." rather than smoothing it into a false claim.

## Word-Friendly Output

- For final thesis body, use clean Markdown that converts predictably to Word; avoid decorative Markdown inside paragraphs.
- When producing standalone polished paragraphs for direct Word paste, output pure Chinese text with Chinese full-width punctuation and no Markdown markers.
- Keep formulas in LaTeX syntax only where the thesis already uses formula blocks or inline variables.
- Avoid excessive bullets in prose chapters. Use tables for structured comparisons and paragraphs for analysis.

## Figure Captions

Chinese thesis captions should be short noun phrases after the figure number:

- Good: `图 5-1 系统总体架构图`
- Good: `图 6-2 地图路线生成流程图`
- Avoid: `图 5-1 本系统清晰展示了整体架构的示意图`

Caption rules:

- Do not include "Figure" or "Table" English prefixes in Chinese thesis captions unless the school template requires bilingual captions.
- Do not start with empty phrases such as "展示了", "描述了", "可以看出". Put the object first.
- For screenshots, include the interface or test target: `图 8-5 地图路线测试结果`.
- For draw.io diagrams, the placeholder should mention the source file: `[此处插入：图 X-X 图名 - 功能说明；正式成稿建议使用 draw.io 源文件 ... 导出为 PNG 或 SVG 后插入]`.
- Keep all figure captions continuous within each chapter and consistent with the appendix export list.

## Table Captions

Chinese table captions should identify the table content directly:

- Good: `表 5-1 用户表结构`
- Good: `表 8-2 功能测试用例表`
- Avoid: `表 5-1 关于用户表中各字段情况的说明`

Table rules:

- Put table titles before tables if the school template does so; otherwise keep one consistent pattern throughout the thesis.
- Use compact column names: "字段名", "类型", "约束", "含义"; "接口", "方法", "功能"; "测试项", "输入", "预期结果", "实际结果".
- Do not put unsupported results in tables. In final thesis text, do not write "待补充" or expose missing-material wording; either provide a supported qualitative result, a formal test method, or move the gap note to a separate audit report for the user.
- For English titles, use concise academic phrases such as "Comparison with", "Ablation study on", or "Results on" only when writing English papers. Chinese undergraduate theses normally use Chinese captions.

## Academic Architecture Diagrams

For draw.io architecture and workflow figures:

- Use white background, clean vector shapes, moderate line widths, and soft academic colors.
- Group related components logically. Prefer left-to-right data flow, top-to-bottom layering, circular loops only when the system truly cycles.
- Keep labels short. Use module names, APIs, data stores, and tools found in the code.
- Do not use photorealistic images, cartoon decoration, heavy shadows, or unreadable text.
- Highlight the core contribution or design decision: for an agent system, show model reasoning, tool execution, state persistence, external services, and frontend rendering as separate but connected parts.

## Reviewer-Style Final Pass

Before final delivery, review like a strict but fair academic reviewer:

- Summary: Can one sentence state the thesis contribution accurately?
- Strengths: Are the real implemented contributions visible, such as multi-agent workflow, tool integration, route visualization, voice input, persistence, or archiving?
- Critical weaknesses: Are there unsupported claims, missing tests, fabricated metrics, mismatched diagrams, inconsistent terminology, or unclear module boundaries?
- Fixability: Distinguish between missing screenshots/data that the user can supplement and structural problems that require rewriting.
- Action guide: Suggest concrete next edits, such as "补充第 8 章测试截图", "将图 5-1 导出为 SVG", or "统一 WebSocket/接口术语".

Do not inflate severity to appear rigorous. If no material issue exists, say the section passes and mention only residual placeholders.

## Advisor-Flagged AI-Sounding Blacklist

Before final delivery, search and rewrite these phrases. They were explicitly criticized in a teacher-reviewed software thesis.

- "根据项目实现" -> use direct evidence or remove the phrase.
- "该图有助于解释" -> introduce the figure naturally before it appears.
- "主要实现以下能力" in a design chapter -> use "该模块承担……职责" for design, or move to implementation.
- "本文围绕……展开" when used as filler -> replace with concrete research content.
- "后端核心类图围绕……展开" -> write what the object relationship means to the business.
- "设计为什么会有实现" risk: never put implementation-flow wording inside a design subsection.
- File names such as state graph scripts, Vue pages, request wrappers, or Python modules should not appear in main body prose.
- Avoid explaining to the reader why a figure is helpful. State the design relationship, then place the figure.

Preferred pattern for figures:

1. Context sentence: "为说明智能规划请求在前端、会话服务和工具服务之间的传递关系，本文绘制时序图，如图 6-1 所示。"
2. Figure.
3. Caption: "图 6-1 智能对话时序图"
4. Analysis paragraph: "由图 6-1 可知，……"

Preferred pattern for implementation code:

1. Explain the business situation.
2. Insert a short code fragment only for the key control logic.
3. Explain how the fragment supports the feature.
4. Do not paste long source files.

- Final thesis body must not contain audit notes about unavailable screenshots, unavailable logs, missing materials, or lack of pressure-test data. Keep those notes outside the thesis or in a private delivery checklist.

## Academic Abstraction Rule

For "design and implementation" undergraduate theses, do not let the paper read like a project introduction, product manual, or feature list.

- Start from the research problem, task abstraction, constraints, design principles, mechanism model, and verification logic.
- Replace product-manual wording such as "用户可以", "系统提供", "页面展示", "功能包括" with academic wording such as "任务链路", "状态转换", "职责边界", "约束建模", "机制设计", "验证维度".
- Requirements chapters should analyze input characteristics, state characteristics, output characteristics, role boundaries, and constraint conditions, not merely list operations.
- Design chapters should explain why a structure is chosen: generation/execution separation, state-driven orchestration, traceable data, maintainable boundaries, security constraints.
- Implementation chapters may mention concrete modules, but each module must be tied to a mechanism: event stream, data transformation, consistency, fallback, persistence, or permission boundary.
- Testing chapters should verify design claims and task-state transitions, not read like a user acceptance checklist.
- Keep necessary software-engineering terms such as function, module, page, and interface only when they are part of formal analysis; avoid piling them into descriptive feature lists.
