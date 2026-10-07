# Markdown Thesis Output Standard

## Primary Rule

Produce one polished Markdown thesis file as the final artifact. Do not generate Word, PDF, or other formats unless the user explicitly asks.

## File Placement

Write the Markdown file to the current project directory or the user-specified output directory. Use a clear filename:

`<论文题目>_毕业论文.md`

## Markdown Structure

Use Word-convertible Markdown:

- `#` for thesis title and top-level non-numbered sections such as 参考文献、致谢、附录.
- `# 第一章 ...` for chapter headings.
- `## 1.1 ...` for first-level sections.
- `### 1.1.1 ...` for second-level subsections.
- Tables in standard Markdown table syntax.
- Formulas in LaTeX block syntax using `$$ ... $$`.
- Diagram placeholders that point to durable draw.io sources or exported images.
- Screenshot and diagram placeholders as normal paragraphs.

Avoid:

- HTML-only layout.
- Styling that only works in one Markdown renderer.
- Auto-generated Word fields.
- Excessive nested bullets that convert poorly to Word.
- Raw structural diagram code blocks in the final thesis body, unless the user explicitly asks to keep diagram source inline.

## Front Matter Sections

A complete thesis Markdown should normally include:

1. Title.
2. Markdown note for later Word conversion, if useful.
3. 摘要.
4. Abstract.
5. 目录 placeholder or manually written table of contents.
6. Main chapters.
7. 参考文献.
8. 致谢.
9. 附录.

## Template-Style Formatting

When a reference PDF or school template is provided, mirror its academic structure in Markdown:

- Match chapter order when compatible with the user's project.
- Use the same level of section granularity.
- Use table captions like `**表 4-1 XXX**`.
- Use figure captions or placeholders like `[此处插入：图4-1 XXX - 说明]`.
- Use formal thesis language, not blog-style explanation.

## Word-Friendly Language

For Chinese thesis text intended for Word conversion:

- Use plain, formal, modern academic Chinese.
- Avoid Markdown emphasis inside paragraphs.
- Avoid empty AI-sounding phrases, exaggerated claims, and ornamental adjectives.
- Keep professional English terms unchanged when they are standard technical names.
- Use Chinese full-width punctuation in Chinese paragraphs, with reasonable spacing around English terms and code identifiers.

## Captions

- Figure captions should be concise noun phrases, such as `图 5-1 系统总体架构图`.
- Table captions should directly identify the table, such as `表 5-1 用户表结构`.
- Do not write captions as full explanatory sentences.
- Every placeholder for a diagram, screenshot, or exported figure must have a visible caption nearby.
- When a draw.io source exists, mention the source path in the placeholder rather than embedding raw diagram code.

## Evidence Markers

Use explicit markers rather than invented claims:

- `待补充信息：...`
- `此处需用户补充截图：...`
- `此处需用户补充测试数据：...`
- `待核验参考文献位：...`

Do not overuse markers in safe chapters; only mark genuinely unsupported facts.

## Final Self-Check

Before reporting completion:

- Confirm the Markdown file exists.
- Confirm it contains all required chapters.
- Confirm no accidental `.docx` or `.pdf` was generated.
- Summarize remaining placeholders the user must fill before Word export.
