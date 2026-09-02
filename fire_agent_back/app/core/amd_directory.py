"""
AMD GPU Cloud 模型目录 — 实时抓取官方 tokenfactory 页面数据（非写死）

数据源: https://developer.amd.com.cn/radeon/tokenfactory?source=cherry-studio
页面实际加载逻辑（从其前端 JS 逆向确认）:
  1) 公共免费区: POST /radeon/api/tokenfactory/bootstrap?directory=true&source=cherry-studio
  2) 专属实例区: GET  /radeon/api/templates?directory=true
  3) 逐卡片 GET detail_url → token_factory 详情（name / model / badge / capability / publisher）

计费层级映射:
  - section=dedicated（badge 为空）           → paid（付费专属实例）
  - badge.tone 含 limited                     → limited_free（限时免费）
  - badge.tone = free                         → free（免费）

结果每次调用实时抓取（无缓存），官方目录调整后立即反映，无需改代码。
"""
import httpx

_AMD_BASE = "https://developer.amd.com.cn"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://developer.amd.com.cn/radeon/tokenfactory?source=cherry-studio",
    "Origin": "https://developer.amd.com.cn",
    "Content-Type": "application/json",
}
_BOOTSTRAP_URL = f"{_AMD_BASE}/radeon/api/tokenfactory/bootstrap?directory=true&source=cherry-studio"
_TEMPLATES_URL = f"{_AMD_BASE}/radeon/api/templates?directory=true"

_CACHE_TTL = 0  # 不缓存，每次实时抓取


def _tier_of(section: str, badge: dict | None) -> str:
    """根据 section + badge 推断计费层级"""
    if section == "dedicated" or not badge:
        return "paid"
    tone = (badge.get("tone") or "").lower()
    if "limited" in tone:
        return "limited_free"
    if tone == "free":
        return "free"
    label = (badge.get("label") or "").lower()
    if "limited" in label:
        return "limited_free"
    if "free" in label:
        return "free"
    return "free"


def _parse_detail(detail: dict, section: str) -> dict | None:
    """
    解析卡片详情 → 统一模型结构

    公共免费详情形如 {"model": {..., "token_factory": {...}}}，
    专属实例详情形如 {"template": {..., "token_factory": {...}}}。
    token_factory.model 是 API 调用时使用的真实模型 ID（如 DeepSeek-V4-Flash），
    token_factory.name 是页面展示名（可能带后缀，如 DeepSeek-V4-Flash-0731）。
    """
    record = detail.get("model") or detail.get("template") or {}
    tf = record.get("token_factory") or {}
    model_id = tf.get("model") or tf.get("name") or record.get("model")
    if not model_id:
        return None
    badge = tf.get("badge")
    sec = tf.get("section") or section
    tier = _tier_of(sec, badge)
    cap = (tf.get("capability") or {}).get("key", "text")
    publisher = (tf.get("publisher") or {}).get("name", "")
    desc = tf.get("description") or record.get("description") or ""
    status = (tf.get("status") or {}).get("label", "")
    return {
        "id": model_id,
        "name": tf.get("name") or model_id,
        "tier": tier,
        "category": "vision" if cap == "vision" else "text",
        "publisher": publisher,
        "desc": desc,
        "status": status,
        "section": sec,
    }


def _fetch_section(url: str, method: str = "GET") -> list[dict]:
    """拉取一个 section 的卡片并逐卡获取详情，返回解析后的模型列表"""
    with httpx.Client(timeout=15, headers=_HEADERS, follow_redirects=True) as client:
        if method == "POST":
            resp = client.post(url, json={})
        else:
            resp = client.get(url)
        resp.raise_for_status()
        payload = resp.json()
        cards = payload.get("cards") or []
        section_key = ((payload.get("section") or payload.get("token_factory_section") or {}).get("key")) or ""

        models = []
        for card in cards:
            detail_url = card.get("detail_url")
            if not detail_url:
                continue
            parsed = None
            for _ in range(2):  # 单卡详情失败重试一次
                try:
                    d = client.get(f"{_AMD_BASE}{detail_url}")
                    d.raise_for_status()
                    parsed = _parse_detail(d.json(), section_key)
                    break
                except Exception:
                    continue
            if parsed:
                models.append(parsed)
        return models


def fetch_amd_directory(force: bool = False) -> list[dict]:
    """
    实时抓取 AMD GPU Cloud 官方模型目录（公共免费 + 专属实例），每次调用均重新请求

    返回统一结构列表:
      {id, name, tier, category, publisher, desc, status, section}
    网络失败等异常时返回空列表（调用方回退到 /models 端点结果）。

    官方目录存在服务端波动（同一模型卡片时有时无），bootstrap 拉取失败自动重试一次。
    """
    # 公共免费区（重试一次） + 专属实例区
    public: list[dict] = []
    dedicated: list[dict] = []
    for attempt in range(2):
        try:
            public = _fetch_section(_BOOTSTRAP_URL, method="POST")
            break
        except Exception:
            if attempt == 1:
                public = []
    try:
        dedicated = _fetch_section(_TEMPLATES_URL)
    except Exception:
        dedicated = []

    models: list[dict] = []
    seen: set[str] = set()
    # 公共免费区在前（同一模型多版本时优先保留免费版本）
    for m in public + dedicated:
        if m["id"] in seen:
            continue
        seen.add(m["id"])
        models.append(m)
    return models
