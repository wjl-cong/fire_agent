# Thesis Diagramming Strategy

## Priority

1. For software-engineering UML diagrams, prefer PlantUML MCP when available. This includes use-case, activity, sequence, class, state, component, deployment, package, and simple C4-style architecture diagrams.
2. Use draw.io/diagrams.net when the user explicitly asks for draw.io, when the diagram needs manual placement, or when the figure is an architecture/data-flow poster-style diagram rather than strict UML.
3. If neither MCP is available, create durable source files in the project: `.puml` for PlantUML diagrams or `.drawio` for diagrams.net diagrams. Export PNG for Markdown-to-Word conversion and keep SVG as a vector backup where possible.
4. For a Word-convertible final thesis, do not leave structural figures as raw Mermaid-only content in the final body. Mermaid is only a private drafting aid unless the user explicitly asks for Mermaid output.

The PlantUML MCP server at https://mcpservers.org/servers/github-com-infobip-plantuml-mcp-server provides PlantUML diagram generation capabilities. Its documented tools are `generate_plantuml_diagram`, `encode_plantuml`, and `decode_plantuml`. The generation tool can return embeddable SVG/PNG URLs and can save local `.svg` or `.png` files through `output_path`; local output is controlled by `PLANTUML_ALLOWED_DIRS`, and the PlantUML service endpoint is controlled by `PLANTUML_SERVER_URL`.

For Word-convertible undergraduate theses, prefer compact diagrams that match A4 portrait pages. Long vertical flowcharts usually look sparse or overflow in Word; replace them with horizontal swimlanes, staged matrices, two-row pipelines, grouped component blocks, or split subfigures. Avoid Mermaid `mindmap` for formal deliverables because support varies across renderers.

When the user asks for all figures to be improved, convert every non-screenshot structural figure in the target chapters to PlantUML or draw.io assets. Prefer PlantUML for strict UML; use draw.io for manually arranged data-flow, dashboard, and architecture composition diagrams. Keep UI and testing figures as screenshot placeholders with captions.

## PlantUML MCP Usage Pattern

When a PlantUML MCP tool is available:

1. Write a concise `.puml` source file based only on verified code, database, API, and user materials.
2. Use `generate_plantuml_diagram` to render both SVG and PNG when possible. Use SVG for inspection and vector backup; embed PNG in Markdown when the target pipeline is Word conversion.
3. Save outputs under a stable thesis directory, such as `thesis/plantuml/` or `docs/figures/plantuml/`.
4. Keep diagram labels short. Put explanations in the caption or body text instead of filling nodes with paragraphs.
5. Validate the rendered image before final delivery. Check that text displays, labels stay inside shapes, arrows do not cross excessively, and the diagram can fit on an A4 page.

Recommended command-level setup when the user wants this MCP installed and network/npm access is allowed:

```bash
npx -y plantuml-mcp-server
```

Common environment variables:

```text
PLANTUML_SERVER_URL=https://www.plantuml.com/plantuml
PLANTUML_ALLOWED_DIRS=/absolute/path/to/project
```

Preferred PlantUML style for theses:

```plantuml
@startuml
skinparam backgroundColor white
skinparam shadowing false
skinparam defaultFontName Microsoft YaHei
skinparam defaultFontSize 14
skinparam ArrowColor #2F3A45
skinparam ActivityBorderColor #2F3A45
skinparam ActivityBackgroundColor #F8FAFC
title Figure X-X Diagram Title
' verified diagram body here
@enduml
```

## draw.io MCP Usage Pattern

When draw.io is the chosen tool and a draw.io MCP tool is available:

1. Search shapes first for cloud, database, UI, API, or UML icons if the tool supports shape search.
2. Create diagram source from verified project architecture.
3. Export or reference a durable `.drawio`, `.svg`, or `.png` artifact if the tool supports it.
4. Insert the Markdown placeholder and artifact path.

If the MCP only returns XML/text, save the XML source as a `.drawio` artifact when feasible. Do not hand-write malformed draw.io XML; validate that diagrams.net can open the file.

## Academic Visual Style

Use a clean thesis style rather than a presentation-poster style:

- Prefer white background, thin neutral strokes, restrained blue/green/gray accent colors, and flat vector shapes.
- Use UML and systems symbols consistently: actor, boundary, control, entity, database cylinder, service component, message arrow, swimlane, package, and cloud only when the verified architecture requires them.
- Keep node labels short, usually 4 to 10 Chinese characters. Move explanation into the caption or body text instead of filling the shape.
- Avoid decorative gradients, heavy shadows, photos, cartoon icons, oversized emojis, and large empty canvases.
- For dense flows, use lanes, grouped blocks, numbered stages, or subfigures so one diagram fits within roughly half to one A4 page when exported to Word.

## Required Thesis Diagrams

For software and intelligent-system theses, strongly consider:

- System architecture diagram.
- Functional module diagram.
- Use-case diagram.
- Key activity diagrams for requirement analysis.
- Core business flowchart.
- Core intelligent-agent/tool-call workflow diagram.
- Login sequence diagram.
- Chat/WebSocket sequence diagram.
- PDF export/archive sequence diagram.
- E-R diagram.
- Class/package/component diagram if code structure is important.
- Deployment diagram if deployment evidence exists.
- Testing screenshots and result figures as placeholders when real screenshots are unavailable.

## Diagram Truth Rules

- Use only modules, tables, APIs, classes, and services found in code or user materials.
- Do not copy diagrams from reference templates unless the structure truly matches the project.
- Do not include unsupported external services or databases.
- For uncertain deployment details, label the diagram as simplified or mark it as "to be supplemented".

## Drafting-Only Mermaid Pattern

Mermaid can be used internally to reason about simple structure, but it should not be the final visible figure format for a polished thesis unless the user explicitly requests it. Replace it with PlantUML or draw.io assets before final delivery.

## Caption Rules

- Figure captions use the thesis template style, such as `Figure 5-1 System Architecture Diagram` or the school-required Chinese equivalent.
- Table captions use the thesis template style, such as `Table 5-1 User Table Structure` or the school-required Chinese equivalent.
- Keep numbering sequential inside each chapter.
- Avoid captions that describe unsupported behavior.
- Every screenshot placeholder and every diagram placeholder must have a caption. Never leave an image, exported diagram, or placeholder without a figure number and title.

## Major Diagram Placeholder

For major diagrams, create or reference a `.puml`, `.png`, `.svg`, or `.drawio` file instead of leaving the body as Mermaid-only.

## Reference DOCX Structure and Black-White UML Rule

When a user provides a reference thesis in DOCX form, extract style patterns rather than project facts:

- Learn chapter organization, heading depth, chapter-summary placement, figure/table density, caption style, and testing-section layout.
- Do not copy the reference project domain, modules, data, results, or references into the target thesis.
- For traditional software-engineering theses, prefer adding chapter summaries such as "本章总结" and a "论文结构" section when the reference template uses them.
- Requirement analysis should contain dense but relevant software-engineering diagrams: use-case, sequence, activity, state, class/interface or data-analysis diagrams as appropriate.
- Design chapters should follow the common order: architecture, function/module structure, database design, component/field/object design, deployment or navigation design.
- For UML and software-engineering diagrams intended for Word, default to black-white professional line art: white background, black borders, black arrows, no gradient, no pastel module fills, no decorative icons, and compact A4-friendly layout.
- Keep color only when the user or school template explicitly requires it; otherwise black-white diagrams are safer for printing, review, and thesis formatting.
