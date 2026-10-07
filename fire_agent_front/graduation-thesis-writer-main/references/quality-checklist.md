# Thesis Quality Checklist

## Truthfulness

- Every function described exists in code, screenshots, docs, or user notes.
- No module from a reference PDF is imported into the thesis unless implemented.
- No performance metric appears without a real test source.
- No experiment conclusion appears without data or logs.
- No reference is fabricated.

## Structure

- The title matches the actual project.
- The abstract names the real stack and implemented functions.
- The outline reflects useful reference-template patterns without copying unsupported template facts.
- The final deliverable is Markdown-only unless the user explicitly requested another format.
- The Markdown heading hierarchy can be converted to Word without manual restructuring.
- The related-technology chapter covers only technologies used by the project.
- Requirement analysis maps to implemented user flows.
- Database design matches models or SQL exactly.
- Interface design uses real routes, methods, and data contracts.
- Testing chapters distinguish completed tests from pending tests.

## Diagrams

- Architecture diagram matches actual frontend, backend, AI/tool, and database boundaries.
- E-R diagram includes only real tables/entities.
- Sequence diagrams follow real request order.
- Flowcharts do not invent branches absent from code.
- Final structural diagrams are draw.io-first: use draw.io MCP when available, or provide diagrams.net-compatible `.drawio` source files when MCP is unavailable.
- Raw Mermaid is not left in the final thesis body for UML, architecture, E-R, DFD, sequence, activity, module, deployment, or algorithm figures unless the user explicitly asks for Mermaid.
- Each diagram has source or a durable generated artifact path plus a thesis-style caption/placeholder.
- Diagram labels are short enough for A4 Word pages and avoid long sentence nodes, oversized vertical chains, heavy shadows, cartoon icons, or low-contrast colors.
- Figure numbering is continuous or marked for final layout.
- Every diagram, screenshot placeholder, exported image, and table has a caption.

## Language

- Terms are consistent across chapters.
- Sentences are formal, objective, and concise.
- Design decisions include rationale.
- Implementation sections explain data flow and control flow.
- Limitations are honest and technically specific.
- Chinese prose is Word-friendly: full-width Chinese punctuation, short paragraphs, no Markdown-only visual tricks that break after Word conversion.
- Remove obvious AI-sounding filler such as exaggerated praise, repetitive "本文首先...然后...最后...", empty "显著提升" claims, and generic large-model slogans without evidence.
- Preserve technical meaning while polishing; do not rewrite grounded implementation details into prettier but unsupported statements.
- Avoid old-fashioned or ornate wording unless the reference template clearly uses it.
- Figure and table titles are concise noun phrases, not long explanatory sentences.

## Final Assembly

- All "待补充" markers are either resolved or intentionally kept.
- Screenshot placeholders are clear enough for the user to capture the right image.
- References are checked against real sources.
- Appendix content does not expose secrets, API keys, or private credentials.
- No automatic `.docx` export is performed unless explicitly requested.
- Run a reviewer-style pass before delivery: separate must-fix truthfulness/logic/format issues from optional wording polish, and do not overclaim when evidence is absent.

## Advisor-Review Gate

Run this gate before delivering a Chinese software graduation thesis:

- Abstract shows workload, method, validation and boundaries; it is not an API-call summary.
- Keywords count is five or fewer.
- Chapter 1.2 is split into foreign research and domestic research.
- Chapter titles avoid unnecessary "与" and "和" stacking.
- Feasibility includes technical, economic, operational, legal compliance, engineering ethics, data security, social health and sustainability when relevant.
- Requirement analysis includes UML/use-case/activity/sequence diagrams inside the corresponding requirement subsections.
- System design does not contain implementation-flow wording.
- System implementation contains the concrete realization and may include a few short code fragments.
- Testing chapter removes generic login-only tests unless authentication is a core contribution.
- Every figure has prior introduction, image/source, caption and follow-up analysis.
- Every table has title and explanation; testing tables follow software testing methods.
- References contain at least 30 academic papers when required, including at least 10 Chinese papers when required.
- Body prose contains no source file paths, no unexplained English type names, and no teacher-flagged AI phrases.
- Policy and legal discussion names concrete laws and articles where possible, especially personal information, sensitive personal information, data security and tourism rights.

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
