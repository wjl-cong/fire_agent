"""
火险等级工具 — 与前端 riskLevel.js 保持一致
"""

COLORS = ["#22d3ee", "#4ade80", "#facc15", "#fb923c", "#ef4444"]


def fire_index_to_level(idx: float) -> int:
    """Final_Fire_Index → 1-5，每 20 一档"""
    if not idx or idx <= 0:
        return 1
    return min(5, max(1, int(idx // 20) + 1))


def risk_score_to_level(score: float) -> int:
    """Risk_Score → 1-5，每 0.2 一档"""
    if score == 0:
        return 1
    return max(1, min(5, __import__("math").ceil(score / 0.2)))


def frp_to_level(frp: float) -> int:
    """FRP → 1-5，每 20 一档"""
    if not frp or frp <= 0:
        return 1
    return min(5, max(1, int(frp // 20) + 1))


def get_color(level: int) -> str:
    """获取等级颜色"""
    l = max(1, min(5, round(level)))
    return COLORS[l - 1]