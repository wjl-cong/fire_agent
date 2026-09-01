/**
 * 轻量级 Markdown → 安全 HTML 渲染器
 *
 * 支持：标题(1-4)、加粗/斜体、行内代码、围栏代码块、表格、无序/有序列表、
 *      引用、分隔线、链接、段落。
 * 所有文本均做 HTML 转义，输出安全，可直接用于 v-html。
 */

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/** 行内样式：输入为已转义文本，处理 `code` / **bold** / *italic* / [link](url) */
function renderInline(text) {
  let t = escapeHtml(text)
  // 行内代码（优先处理，避免代码内容被误解析）
  t = t.replace(/`([^`\n]+)`/g, (m, c) => `<code>${c}</code>`)
  // 加粗
  t = t.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
  t = t.replace(/__([^_\n]+)__/g, '<strong>$1</strong>')
  // 斜体
  t = t.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>')
  t = t.replace(/(^|[^_])_([^_\n]+)_(?!_)/g, '$1<em>$2</em>')
  // 链接（仅允许 http/https/mailto，杜绝 javascript:）
  t = t.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+|mailto:[^\s)]+)\)/g,
    (m, label, url) => `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${label}</a>`)
  return t
}

function splitTableRow(line) {
  let s = line.trim()
  if (s.startsWith('|')) s = s.slice(1)
  if (s.endsWith('|')) s = s.slice(0, -1)
  return s.split('|').map(c => c.trim())
}

export function renderMarkdown(md) {
  if (!md) return ''
  const lines = String(md).replace(/\r\n/g, '\n').split('\n')
  const out = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    // ===== 围栏代码块 =====
    if (/^```/.test(line.trim())) {
      const lang = line.trim().slice(3).trim()
      const buf = []
      i++
      while (i < lines.length && !/^```/.test(lines[i].trim())) {
        buf.push(lines[i])
        i++
      }
      i++ // 跳过结束 ```
      out.push(`<pre><code${lang ? ` class="language-${escapeHtml(lang)}"` : ''}>${escapeHtml(buf.join('\n'))}</code></pre>`)
      continue
    }

    // ===== 表格 =====
    if (line.trim().startsWith('|') && i + 1 < lines.length &&
        /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1]) && lines[i + 1].includes('-')) {
      const headerCells = splitTableRow(line)
      const align = splitTableRow(lines[i + 1]).map(cell => {
        const c = cell.trim()
        if (c.startsWith(':') && c.endsWith(':')) return 'center'
        if (c.endsWith(':')) return 'right'
        if (c.startsWith(':')) return 'left'
        return 'left'
      })
      i += 2
      const bodyRows = []
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        bodyRows.push(splitTableRow(lines[i]))
        i++
      }
      let html = '<div class="md-table-wrap"><table>'
      html += '<thead><tr>' + headerCells.map((c, idx) =>
        `<th style="text-align:${align[idx] || 'left'}">${renderInline(c)}</th>`).join('') + '</tr></thead>'
      html += '<tbody>' + bodyRows.map(row => '<tr>' + row.map((c, idx) =>
        `<td style="text-align:${align[idx] || 'left'}">${renderInline(c)}</td>`).join('') + '</tr>').join('') + '</tbody>'
      html += '</table></div>'
      out.push(html)
      continue
    }

    // ===== 标题 =====
    const h = line.match(/^(#{1,4})\s+(.*)$/)
    if (h) {
      out.push(`<h${h[1].length}>${renderInline(h[2])}</h${h[1].length}>`)
      i++
      continue
    }

    // ===== 分隔线 =====
    if (/^\s*([-*_])\s*(\1\s*){2,}$/.test(line)) {
      out.push('<hr />')
      i++
      continue
    }

    // ===== 无序列表 =====
    if (/^\s*[-*+]\s+/.test(line)) {
      const items = []
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
        items.push(renderInline(lines[i].replace(/^\s*[-*+]\s+/, '')))
        i++
      }
      out.push('<ul>' + items.map(it => `<li>${it}</li>`).join('') + '</ul>')
      continue
    }

    // ===== 有序列表 =====
    if (/^\s*\d+\.\s+/.test(line)) {
      const items = []
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(renderInline(lines[i].replace(/^\s*\d+\.\s+/, '')))
        i++
      }
      out.push('<ol>' + items.map(it => `<li>${it}</li>`).join('') + '</ol>')
      continue
    }

    // ===== 引用 =====
    if (/^\s*>\s?/.test(line)) {
      const buf = []
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        buf.push(lines[i].replace(/^\s*>\s?/, ''))
        i++
      }
      out.push(`<blockquote>${renderInline(buf.join(' '))}</blockquote>`)
      continue
    }

    // ===== 空行 =====
    if (line.trim() === '') {
      i++
      continue
    }

    // ===== 普通段落（合并连续非空非块级行） =====
    const buf = []
    while (i < lines.length && lines[i].trim() !== '' &&
           !/^```/.test(lines[i].trim()) &&
           !/^(#{1,4})\s+/.test(lines[i]) &&
           !/^\s*[-*+]\s+/.test(lines[i]) &&
           !/^\s*\d+\.\s+/.test(lines[i]) &&
           !/^\s*>\s?/.test(lines[i]) &&
           !lines[i].trim().startsWith('|')) {
      buf.push(lines[i])
      i++
    }
    out.push(`<p>${renderInline(buf.join(' '))}</p>`)
  }

  return out.join('\n')
}

export default renderMarkdown
