/**
 * @fileoverview 火险等级统一映射工具
 *
 * 等级规则（全系统一致）：
 *   - Final_Fire_Index 每 20 一档：0-20→1, 20-40→2, 40-60→3, 60-80→4, 80+→5
 *   - Risk_Score 每 0.2 一档：0-0.2→1, 0.2-0.4→2, 0.4-0.6→3, 0.6-0.8→4, 0.8-1.0→5
 *   - FRP 每 20 一档（同 Final_Fire_Index）
 *
 * 颜色（与 gis-theme.css 变量保持一致）：
 *   1=青 #22d3ee  2=绿 #4ade80  3=黄 #facc15  4=橙 #fb923c  5=红 #ef4444
 */

// ==================== 颜色常量 ====================
export const RISK_COLORS = ['#22d3ee', '#4ade80', '#facc15', '#fb923c', '#ef4444']
export const RISK_FILL_ALPHA = '50'
export const RISK_COLORS_FILL = RISK_COLORS.map(c => c + RISK_FILL_ALPHA)

/** 获取指定等级的颜色（1-5，越界回退到 1 级） */
export const getRiskColor = (level) => {
    const l = Math.max(1, Math.min(5, Math.round(level)))
    return RISK_COLORS[l - 1] || RISK_COLORS[0]
}

// ==================== 等级转换函数 ====================

/** Final_Fire_Index → 1-5，每 20 一档 */
export const fireIndexToLevel = (idx) => {
    if (!idx || idx <= 0) return 1
    return Math.min(5, Math.max(1, Math.floor(Number(idx) / 20) + 1))
}

/** Risk_Score → 1-5，每 0.2 一档 */
export const riskScoreToLevel = (score) => {
    const s = Number(score)
    if (s === 0) return 1
    return Math.max(1, Math.min(5, Math.ceil(s / 0.2)))
}

/** FRP → 1-5，每 20 一档（同 fireIndexToLevel） */
export const frpToRiskLevel = (frp) => {
    const f = Number(frp)
    if (!Number.isFinite(f) || f <= 0) return 1
    return Math.min(5, Math.max(1, Math.floor(f / 20) + 1))
}

/** 置信度兜底映射（无 FRP 时使用） */
export const CONF_FALLBACK_LEVEL = { low: 2, nominal: 3, high: 5 }

/** Risk_Score → 等级完整信息（便捷合并） */
export const getLevelInfoByScore = (score) => {
    const level = riskScoreToLevel(score)
    return {...getLevelInfo(level), level }
}

/** Final_Fire_Index → 等级完整信息（便捷合并） */
export const getLevelInfoByFireIndex = (fireIndex) => {
    const level = fireIndexToLevel(fireIndex)
    return {...getLevelInfo(level), level }
}

// ==================== 等级描述信息 ====================

const LEVEL_INFO_MAP = {
    1: {
        label: '1级 正常',
        desc: '火险风险低，植被燃烧风险极低，当前气象条件下适宜户外活动。',
        measure: '正常生产生活，保持基本用火安全意识即可。'
    },
    2: {
        label: '2级 注意',
        desc: '火险风险较低，但部分时段和区域需保持警惕，干季高风险区尤需关注。',
        measure: '建议加强林区日常巡查，禁止野外违规用火，发现火情立即上报。'
    },
    3: {
        label: '3级 警告',
        desc: '火险风险已达中等水平，部分州市进入警戒状态，植被干燥易燃。',
        measure: '停止一切野外用火行为，护林员加密巡山频次，设卡检查进入林区人员。'
    },
    4: {
        label: '4级 高度',
        desc: '火险风险高，火灾发生概率显著上升，多地已处于高度戒备状态。',
        measure: '全面禁火管控，护林员24小时值班值守，禁止一切野外用火和林事活动。'
    },
    5: {
        label: '5级 极度',
        desc: '极度危险！火险指数达到极限，极易引发森林火灾，必须采取最高级别防控措施。',
        measure: '全面封山禁火，启动最高级别防火应急预案，禁止一切人员进入林区。'
    }
}

/** 获取等级完整信息（含颜色、描述、措施） */
export const getLevelInfo = (level) => {
    const l = Math.max(1, Math.min(5, Math.round(level)))
    return { level: l, color: RISK_COLORS[l - 1], ...LEVEL_INFO_MAP[l] }
}

// ==================== 整体摘要映射 ====================

export const SUMMARY_MAP = {
    1: { label: '正常', color: RISK_COLORS[0], icon: '🟢', summary: '全省火险形势平稳，无明显风险区域，可正常开展各项生产活动。' },
    2: { label: '注意', color: RISK_COLORS[1], icon: '🟡', summary: '需引起关注，建议加强火源管控和日常巡护。' },
    3: { label: '警告', color: RISK_COLORS[2], icon: '🟠', summary: '全省火险等级升至警告水平，需强化防控措施。' },
    4: { label: '高度', color: RISK_COLORS[3], icon: '🔴', summary: '全省火险形势严峻，需全面戒备。' },
    5: { label: '极度', color: RISK_COLORS[4], icon: '⛔', summary: '全省已处于极度危险状态！建议立即启动最高级别应急预案。' }
}