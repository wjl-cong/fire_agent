/**
 * @fileoverview ECharts 配色主题常量
 * 与系统 CSS 变量 (gis-theme.css) 保持一致
 *
 * 火险等级颜色已迁移至 riskLevel.js 统一管理，此处 re-export 保持向后兼容
 */

import { RISK_COLORS } from '@/utils/riskLevel'

// ECharts 全局配色（深色主题）
export const gisChartPalette = {
    text: "#94a3b8", // 刻度/图例文字
    textStrong: "#f8fafc", // 弹层标题文字
    axis: "#334155", // 坐标轴/分割线
    split: "#1e293b", // 网格线
    bgTooltip: "rgba(15, 23, 42, 0.95)", // 弹层背景
};

// 火险等级五色，1=青 2=绿 3=黄 4=橙 5=红（从 riskLevel.js 统一读取）
export const riskLevelColors = RISK_COLORS