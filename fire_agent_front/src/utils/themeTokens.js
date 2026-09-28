/**
 * 主题取色工具 — 供 JS 侧（ECharts 配置、canvas、动态样式）读取当前主题的 CSS 变量
 *
 * CSS 变量无法直接在 JS 中引用，图表等需要显式取色；主题切换后需重新取值并重建图表。
 * 用法：
 *   import { chartTokens } from '@/utils/themeTokens'
 *   import { useThemeStore } from '@/stores/theme'
 *   const theme = useThemeStore()
 *   watch(() => theme.mode, () => { buildChart(chartTokens()) })
 */

/** 读取 :root 上的 CSS 变量（未定义时返回 fallback） */
export function cssVar(name, fallback = '') {
  try {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
    return v || fallback
  } catch (e) {
    return fallback
  }
}

/** 图表常用主题色集合（每次调用实时取值，主题切换后立即生效） */
export function chartTokens() {
  return {
    text: cssVar('--gis-text', '#0f172a'),
    muted: cssVar('--gis-text-muted', '#64748b'),
    border: cssVar('--gis-border', 'rgba(100, 116, 139, 0.28)'),
    panel: cssVar('--gis-bg-panel-2', 'rgba(255, 255, 255, 0.94)'),
    accent: cssVar('--gis-accent', '#2563eb'),
    axis: cssVar('--gis-text-muted', '#64748b'),
    split: cssVar('--gis-border', 'rgba(100, 116, 139, 0.28)'),
  }
}