# Reference Template Learning

## Purpose

Use this reference when the user provides thesis PDFs, Word templates, school format documents, prior excellent theses, or sample graduation designs. The goal is to learn reusable thesis-writing patterns while keeping all project facts grounded in the user's own code and materials.

## What To Learn

Extract and reuse:

- Overall chapter order and whether the school prefers "可行性分析" as an independent chapter or part of "需求分析".
- Heading depth, numbering habits, and title wording style.
- Whether the template uses Chinese chapter numerals, Arabic section numbers, table captions like "表 1", or figure captions like "图 4".
- Abstract structure, keyword count, and English abstract style.
- Literature-review density and whether it is grouped by method, domain, or chronology.
- How related technologies are introduced: short principle, reason for selection, and project usage.
- How requirement analysis is written: user roles, use cases, flowcharts, non-functional needs.
- How design chapters are organized: architecture, module structure, database design, interface design.
- How implementation chapters balance screenshots, module text, and key code explanation.
- How testing chapters present environment, test cases, screenshots, results, and conclusion.
- Figure/table caption pattern and placeholder wording.
- Diagram density, UML type selection, page-fit habits, and whether large diagrams are split into subfigures.
- Word-oriented Chinese style: paragraph length, punctuation habits, sentence density, transition wording, and how the template avoids slogan-like expression.
- Table-title wording, table column naming, and whether the template uses "测试用例表", "接口设计表", "数据库表结构" or similar title patterns.
- Page-level formatting constraints, if stated by the school template.
- Markdown-to-Word implications: which parts should become headings, captions, tables, formulas, or image placeholders.

## What Not To Copy

Never transfer these from reference templates into the user's thesis unless independently supported:

- System functions, user roles, database tables, interfaces, or modules.
- Algorithm names, model structures, datasets, metrics, or experiment conclusions.
- Test results, performance numbers, deployment environment, screenshots, or logs.
- References and citations that have not been verified for the user's topic.
- Domain background that does not match the user's project.

## Template Audit Output

When templates are available, include a short "参考模板学习结果" section in the material audit:

- 模板类型：学校格式模板 / 优秀论文 / 同类系统论文 / 算法研究论文 / 混合材料。
- 可借鉴结构：list the useful chapter or section patterns.
- 可借鉴写法：list tone, paragraph density, figure/table style, testing style.
- Markdown排版迁移策略：state how template conventions will be represented in Markdown.
- 不可迁移内容：list template-specific facts that must not enter the thesis.
- 对本论文大纲的影响：explain how the outline will adapt to the project.

## Adapting Multiple Templates

If several templates conflict:

1. Prefer the user's school template for formatting and required sections.
2. Prefer a same-project-type thesis for system-analysis and implementation structure.
3. Prefer high-quality academic papers for literature review and formal language.
4. Prefer the user's code over all templates for actual technical content.

## Example Adaptation Rule

If a reference thesis has a deep-learning model chapter but the user's project uses a large-model agent without model training, do not create a fake model-training chapter. Rename it to "核心流程与关键技术实现" and discuss the real agent workflow, tool invocation, prompt constraints, state persistence, route generation, and external-service integration.

## Reference DOCX Structure and Black-White UML Rule

When a user provides a reference thesis in DOCX form, extract style patterns rather than project facts:

- Learn chapter organization, heading depth, chapter-summary placement, figure/table density, caption style, and testing-section layout.
- Do not copy the reference project domain, modules, data, results, or references into the target thesis.
- For traditional software-engineering theses, prefer adding chapter summaries such as "本章总结" and a "论文结构" section when the reference template uses them.
- Requirement analysis should contain dense but relevant software-engineering diagrams: use-case, sequence, activity, state, class/interface or data-analysis diagrams as appropriate.
- Design chapters should follow the common order: architecture, function/module structure, database design, component/field/object design, deployment or navigation design.
- For UML and software-engineering diagrams intended for Word, default to black-white professional line art: white background, black borders, black arrows, no gradient, no pastel module fills, no decorative icons, and compact A4-friendly layout.
- Keep color only when the user or school template explicitly requires it; otherwise black-white diagrams are safer for printing, review, and thesis formatting.
