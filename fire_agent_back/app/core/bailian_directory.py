"""
阿里百炼免费额度模型目录 — 实时解析官方计费文档（无需登录）

数据源: https://help.aliyun.com/zh/model-studio/model-pricing（模型调用价格）
该文档由阿里云官方持续维护，每个模型的计费表格都带「免费额度」列
（如 100 万 Token）与有效期说明（如 开通后 90 天内），覆盖：
  文本生成（千问/开源版/第三方）、语音合成、语音识别、语音对话、文本向量等。

页面数据内嵌于 window.__ICE_PAGE_PROPS__（服务端渲染），程序可直接抓取解析，
官方新增/调整免费额度模型后目录自动跟随，无需改代码。

注：控制台「免费额度剩余量/过期时间/状态」为账号级数据（需登录态），
由 admin.py 的 /bailian/quota 端点配合用户 Cookie 实时获取，本模块只提供公开目录。
"""
import re
import time

import httpx

_PRICING_URL = "https://help.aliyun.com/zh/model-studio/model-pricing"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

_CACHE_TTL = 300  # 缓存 5 分钟（文档约 600KB，避免每次点击都拉全量）
_cache: dict = {"ts": 0.0, "models": []}

_RE_H = re.compile(r"<h([23])[^>]*>(.*?)</h\1>", re.S)
_RE_TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_RE_TD = re.compile(r"<td([^>]*)>(.*?)</td>", re.S)
_RE_TH = re.compile(r"<th[^>]*>(.*?)</th>", re.S)
_RE_TAG = re.compile(r"<[^>]+>")
_RE_MODEL = re.compile(r"[a-zA-Z][a-zA-Z0-9]*(?:[.\-][a-zA-Z0-9]+)+")


def _clean(html: str) -> str:
    """去标签 + 压缩空白"""
    text = _RE_TAG.sub(" ", html)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", text).strip()


def _extract_page_props(html: str) -> str | None:
    """从页面 HTML 中提取 __ICE_PAGE_PROPS__ 的 JSON（括号配对）"""
    key = "window.__ICE_PAGE_PROPS__="
    i = html.find(key)
    if i < 0:
        return None
    j = html.find("{", i)
    depth, k, in_str, esc = 0, j, False, False
    while k < len(html):
        c = html[k]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
        k += 1
    return html[j:k + 1]


def _category_of(h2: str, h3: str) -> str:
    """根据章节标题推断模型分类（text/vision/multimodal/audio/embedding/other）"""
    t = f"{h2} {h3}"
    if "向量" in h2 or "向量" in h3:
        return "embedding"
    if "语音" in h2 or "音频" in h2:
        return "audio"
    if "图像" in t or "视频" in t or "音乐" in t or "3D" in t or "涂鸦" in t or "重绘" in t:
        return "other"
    if "omni" in t.lower():
        return "multimodal"
    if any(k in t for k in ("VL", "OCR", "QVQ", "视觉")):
        return "vision"
    if "Audio" in t:
        return "audio"
    if "文本生成" in h2 or "行业" in h2 or "排序" in h2:
        return "text"
    return "other"


def _parse_free_models(content: str) -> list[dict]:
    """
    遍历文档 HTML：按 h2/h3 章节定位分类，逐表格行解析模型 ID + 免费额度单元格

    表结构（实测）:
      <thead><tr>...<th>免费额度（注）<sup>有效期：...90 天内...</sup></th></tr></thead>
      <tbody><tr><td rowspan=3>模型ID</td>...<td>100 万 Token</td></tr>...
    无免费额度的行（「无免费额度」/空）跳过，只保留有免费额度的模型。
    """
    models: list[dict] = []
    seen: set[str] = set()
    h2, h3 = "", ""
    quota_col = -1          # 当前表格「免费额度」列下标
    validity = "以控制台为准"
    days = 90
    pending_model, pending_left = "", 0  # 模型单元格 rowspan 处理

    # 顺序扫描：标题与行混合（用 finditer 拼接正则）
    token_re = re.compile(r"<h([23])[^>]*>(.*?)</h\1>|<tr[^>]*>(.*?)</tr>", re.S)
    for m in token_re.finditer(content):
        if m.group(1):  # h2/h3 标题
            title = _clean(m.group(2))
            if m.group(1) == "2":
                h2, h3 = title, ""
            else:
                h3 = title
            quota_col, pending_model, pending_left = -1, "", 0
            continue

        row = m.group(3)
        ths = _RE_TH.findall(row)
        if ths:  # 表头：定位「免费额度」列 + 解析有效期
            quota_col = -1
            for idx, th in enumerate(ths):
                if "免费额度" in th:
                    quota_col = idx
                    v = re.search(r"有效期：.{0,60}?(\d+)\s*<[^>]*>\s*天|有效期：.{0,60}?(\d+)\s*天", _clean(th))
                    d = re.search(r"(\d+)\s*天", _clean(th))
                    if d:
                        days = int(d.group(1))
                        validity = f"{days}天"
            pending_model, pending_left = "", 0
            continue

        cells_html = [c[1] for c in _RE_TD.findall(row)]
        if not cells_html:
            continue
        cells = [_clean(c) for c in cells_html]

        # 模型 ID 单元格（首列，可能带 rowspan 跨行备注）
        first_attr = _RE_TD.findall(row)[0][0]
        model_id = ""
        rowspan = 1
        rs = re.search(r'rowspan="(\d+)"', first_attr)
        if rs:
            rowspan = int(rs.group(1))
        mm = _RE_MODEL.search(cells[0]) if cells else None
        if mm:
            model_id = mm.group(0)
            pending_model, pending_left = model_id, rowspan - 1
        elif pending_left > 0:
            model_id, pending_left = pending_model, pending_left - 1
        if not model_id:
            continue

        # 免费额度单元格
        if quota_col < 0 or quota_col >= len(cells):
            continue
        quota_text = cells[quota_col]
        if not quota_text or "无免费额度" in quota_text:
            continue
        if not (re.search(r"\d", quota_text) or "免费" in quota_text):
            continue

        if model_id in seen:
            continue
        seen.add(model_id)
        category = _category_of(h2, h3)
        if category == "other":
            continue
        models.append({
            "model": model_id,
            "category": category,
            "quota": quota_text,
            "validity": validity,
            "days": days,
            "desc": (h3 or h2).strip(),
        })
    return models


def fetch_bailian_free_models(force: bool = False) -> list[dict]:
    """
    实时获取百炼免费额度模型目录

    返回:
      [{model, category, quota, validity, days, desc}, ...]
    抓取/解析失败时返回空列表（调用方回退到内置静态目录）。
    """
    global _cache
    now = time.time()
    if not force and _cache["models"] and now - _cache["ts"] < _CACHE_TTL:
        return _cache["models"]

    models: list[dict] = []
    try:
        resp = httpx.get(_PRICING_URL, headers=_HEADERS, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        raw = _extract_page_props(resp.text)
        if raw:
            # __ICE_PAGE_PROPS__ 是合法 JSON，直接解析取 content 字段
            import json
            data = json.loads(raw)
            content = (data.get("docDetailData", {}).get("storeData", {}).get("data", {}) or {}).get("content", "")
            if content:
                models = _parse_free_models(content)
    except Exception:
        models = []

    if models:
        _cache = {"ts": now, "models": models}
    return models
