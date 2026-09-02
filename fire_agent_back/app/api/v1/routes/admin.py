"""
系统管理接口 — 数据源配置 / 模型接入 / Agent 参数 / 系统日志 / 用户权限管理
"""
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
import dotenv
from sqlalchemy.orm import Session

from app.core.amd_directory import fetch_amd_directory
from app.core.bailian_directory import fetch_bailian_free_models
from app.core.bailian_quota_data import get_bailian_account_quota
from app.core.config import settings
from app.core.database import get_db
from app.core.llm import is_qwen3_8_available, list_provider_models
from app.core.security import get_current_user, get_current_admin
from app.models.user import User
from app.schemas.admin import ConfigUpdate, RoleUpdate

router = APIRouter()

# ====== 简易系统日志（内存环形缓冲） ======
_SYSTEM_LOGS = []
_MAX_LOGS = 200


def log_system_event(source: str, message: str, level: str = "INFO"):
    """记录一条系统日志（供其他模块调用）"""
    _SYSTEM_LOGS.insert(0, {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "level": level,
        "source": source,
        "message": message,
    })
    if len(_SYSTEM_LOGS) > _MAX_LOGS:
        _SYSTEM_LOGS.pop()


# ====== Agent 参数（内存态，可从环境默认值覆盖） ======
AGENT_CONFIG = {
    "orchestrator_temperature": 0.2,
    "report_temperature": 0.4,
    "max_agents": 5,
}

# ====== 阿里百炼免费额度模型目录（新用户开通即送；额度政策可能调整，以百炼控制台为准） ======
# category: text=大语言 / vision=视觉 / multimodal=全模态 / audio=语音 / embedding=向量
BAILIAN_FREE_MODELS = {
    # ---- 大语言模型 ----
    "qwen-flash":        {"name": "Qwen-Flash 极速版",   "quota": "100万 tokens", "validity": "180天", "days": 180, "category": "text", "desc": "速度最快、成本最低，适合智能查询意图解析"},
    "qwen-turbo":        {"name": "Qwen-Turbo 标准版",   "quota": "100万 tokens", "validity": "180天", "days": 180, "category": "text", "desc": "均衡性价比，适合高频调用"},
    "qwen-plus":         {"name": "Qwen-Plus 增强版",    "quota": "100万 tokens", "validity": "180天", "days": 180, "category": "text", "desc": "效果与性能均衡，系统默认模型"},
    "qwen-max":          {"name": "Qwen-Max 旗舰版",     "quota": "100万 tokens", "validity": "180天", "days": 180, "category": "text", "desc": "最强推理能力，适合报告生成"},
    "qwen-long":         {"name": "Qwen-Long 长文本",    "quota": "100万 tokens", "validity": "180天", "days": 180, "category": "text", "desc": "超长上下文，适合大文档处理"},
    "deepseek-v3":       {"name": "DeepSeek-V3",         "quota": "100万 tokens", "validity": "180天", "days": 180, "category": "text", "desc": "DeepSeek 通用对话模型"},
    "deepseek-r1":       {"name": "DeepSeek-R1 推理版",  "quota": "100万 tokens", "validity": "180天", "days": 180, "category": "text", "desc": "深度推理，适合复杂分析"},
    "qwq-plus":          {"name": "QwQ-Plus 推理版",     "quota": "100万 tokens", "validity": "180天", "days": 180, "category": "text", "desc": "Qwen 推理增强模型"},
    "qwen3-235b-a22b":   {"name": "Qwen3-235B-A22B",     "quota": "100万 tokens", "validity": "90天",  "days": 90,  "category": "text", "desc": "Qwen3 旗舰 MoE 大模型"},
    "qwen3-32b":         {"name": "Qwen3-32B",           "quota": "100万 tokens", "validity": "90天",  "days": 90,  "category": "text", "desc": "Qwen3 中等规模"},
    "qwen3-30b-a3b":     {"name": "Qwen3-30B-A3B",       "quota": "100万 tokens", "validity": "90天",  "days": 90,  "category": "text", "desc": "Qwen3 MoE 高性价比"},
    "qwen3-14b":         {"name": "Qwen3-14B",           "quota": "100万 tokens", "validity": "90天",  "days": 90,  "category": "text", "desc": "Qwen3 轻量版"},
    "qwen3-8b":          {"name": "Qwen3-8B",            "quota": "100万 tokens", "validity": "90天",  "days": 90,  "category": "text", "desc": "Qwen3 轻量版"},
    "qwen3-4b":          {"name": "Qwen3-4B",            "quota": "100万 tokens", "validity": "90天",  "days": 90,  "category": "text", "desc": "Qwen3 极轻量"},
    # ---- 视觉模型 ----
    "qwen-vl-plus":              {"name": "Qwen-VL-Plus",         "quota": "100万 tokens", "validity": "180天", "days": 180, "category": "vision", "desc": "图文理解主力模型"},
    "qwen-vl-max":               {"name": "Qwen-VL-Max",          "quota": "100万 tokens", "validity": "180天", "days": 180, "category": "vision", "desc": "视觉理解旗舰"},
    "qwen2.5-vl-72b-instruct":   {"name": "Qwen2.5-VL-72B",       "quota": "100万 tokens", "validity": "90天",  "days": 90,  "category": "vision", "desc": "开源视觉大模型 72B"},
    "qwen2.5-vl-32b-instruct":   {"name": "Qwen2.5-VL-32B",       "quota": "100万 tokens", "validity": "90天",  "days": 90,  "category": "vision", "desc": "开源视觉大模型 32B"},
    "qvq-plus":                  {"name": "QvQ-Plus 视觉推理",     "quota": "100万 tokens", "validity": "90天",  "days": 90,  "category": "vision", "desc": "视觉推理增强"},
    "qwen3-vl-plus":             {"name": "Qwen3-VL-Plus",        "quota": "100万 tokens", "validity": "90天",  "days": 90,  "category": "vision", "desc": "Qwen3 视觉理解"},
    # ---- 全模态模型 ----
    "qwen-omni-turbo":  {"name": "Qwen-Omni-Turbo",     "quota": "100万 tokens", "validity": "180天", "days": 180, "category": "multimodal", "desc": "文本+图像+音频全模态理解"},
    "qwen-omni-plus":   {"name": "Qwen-Omni-Plus",      "quota": "100万 tokens", "validity": "180天", "days": 180, "category": "multimodal", "desc": "全模态旗舰"},
    "qwen3-omni-flash": {"name": "Qwen3-Omni-Flash",    "quota": "100万 tokens", "validity": "90天",  "days": 90,  "category": "multimodal", "desc": "Qwen3 全模态极速版"},
    # ---- 语音模型 ----
    "qwen-tts":            {"name": "Qwen-TTS 语音合成",       "quota": "限时免费", "validity": "以控制台为准", "days": 90, "category": "audio", "usage": "tts", "desc": "文本转语音"},
    "qwen3-tts-flash":     {"name": "Qwen3-TTS-Flash",         "quota": "限时免费", "validity": "以控制台为准", "days": 90, "category": "audio", "usage": "tts", "desc": "新一代语音合成"},
    "cosyvoice-v2":        {"name": "CosyVoice-2 语音合成",     "quota": "限时免费", "validity": "以控制台为准", "days": 90, "category": "audio", "usage": "tts", "desc": "情感语音合成"},
    "paraformer-v2":       {"name": "Paraformer-V2 识别",       "quota": "限时免费", "validity": "以控制台为准", "days": 90, "category": "audio", "usage": "asr", "desc": "语音识别"},
    "qwen3-asr-flash":     {"name": "Qwen3-ASR-Flash 识别",    "quota": "限时免费", "validity": "以控制台为准", "days": 90, "category": "audio", "usage": "asr", "desc": "新一代语音识别"},
    # ---- 向量模型（RAG Embedding） ----
    "text-embedding-v3":  {"name": "Text-Embedding-V3",  "quota": "100万 tokens", "validity": "180天", "days": 180, "category": "embedding", "desc": "系统 RAG 默认向量模型（1024维）"},
    "text-embedding-v4":  {"name": "Text-Embedding-V4",  "quota": "100万 tokens", "validity": "180天", "days": 180, "category": "embedding", "desc": "新一代向量模型（多维度）"},
}

# 免费额度模型分类展示名称
MODEL_CATEGORIES = {
    "text": "大语言模型",
    "vision": "视觉模型",
    "multimodal": "全模态模型",
    "audio": "语音模型",
    "embedding": "向量模型",
}

# 百炼控制台直达链接（免费额度各分类页 + 高校权益）
BAILIAN_CONSOLE_URLS = {
    "console": "https://bailian.console.aliyun.com",
    "free_text": "https://bailian.console.aliyun.com/cn-beijing?tab=costing-balance#/costing-balance/free-quota?modelType=Text",
    "free_vision": "https://bailian.console.aliyun.com/cn-beijing?tab=costing-balance#/costing-balance/free-quota?modelType=Vision",
    "free_multimodal": "https://bailian.console.aliyun.com/cn-beijing?tab=costing-balance#/costing-balance/free-quota?modelType=Multimodal",
    "free_audio": "https://bailian.console.aliyun.com/cn-beijing?tab=costing-balance#/costing-balance/free-quota?modelType=Audio",
    "free_embedding": "https://bailian.console.aliyun.com/cn-beijing?tab=costing-balance#/costing-balance/free-quota?modelType=Embedding",
    "usage": "https://bailian.console.aliyun.com/cn-beijing?tab=costing-balance#/costing-balance",
    "aliyun_benefit": "https://home.console.aliyun.com/home/dashboard/Benefit",
}

# ====== AMD GPU Cloud ======
# 模型目录实时抓取自官方 tokenfactory 页面（app/core/amd_directory.py），
# 计费层级（免费/限时免费/付费）由官方 badge/section 自动标注，不做本地写死。
# tier 展示名称
AMD_TIER_NAMES = {"free": "免费", "limited_free": "限时免费", "paid": "付费"}

# AMD 开发者控制台直达链接
AMD_CONSOLE_URLS = {
    "console": "https://developer.amd.com.cn/",
    "models": "https://developer.amd.com.cn/radeon",
    "usage": "https://developer.amd.com.cn/",
}

# ====== 配置脱敏 ======
def _mask(key: str) -> str:
    """敏感字段脱敏"""
    if key and len(key) > 8:
        return key[:3] + "****" + key[-3:]
    return key or ""


def _current_config() -> dict:
    """返回去敏的当前配置 + Agent 参数"""
    return {
        "datasource": {
            "database_url": settings.DATABASE_URL.split("@")[-1],
            "amap_key": _mask(settings.AMAP_KEY),
        },
        "model": {
            "active_provider": settings.ACTIVE_LLM_PROVIDER,
            # 阿里云 / 通用 OpenAI
            "llm_api_key": _mask(settings.LLM_API_KEY),
            "llm_api_base": settings.LLM_API_BASE,
            "llm_model": settings.LLM_MODEL,
            "embedding_model": settings.EMBEDDING_MODEL,
            # 视觉 / 语音模型
            "vision_provider": settings.VISION_PROVIDER,
            "vision_model": settings.VISION_MODEL,
            "asr_model": settings.ASR_MODEL,
            "tts_model": settings.TTS_MODEL,
            # AMD GPU Cloud
            "amd_api_key": _mask(settings.AMD_API_KEY),
            "amd_api_base": settings.AMD_API_BASE,
            "amd_model": settings.AMD_MODEL,
            # 本地 Ollama
            "ollama_api_base": settings.OLLAMA_API_BASE,
            "ollama_model": settings.OLLAMA_MODEL,
            # Qwen3.8-Flash-Next 时间窗口
            "qwen3_8_flash_start": settings.QWEN3_8_FLASH_START,
            "qwen3_8_flash_end": settings.QWEN3_8_FLASH_END,
            "qwen3_8_available": is_qwen3_8_available(),
        },
        "rag": {
            "kb_chunk_size": settings.KB_CHUNK_SIZE,
            "kb_chunk_overlap": settings.KB_CHUNK_OVERLAP,
            "kb_top_k": settings.KB_TOP_K,
        },
        "agent": dict(AGENT_CONFIG),
    }


@router.get("/config")
async def get_config(current: User = Depends(get_current_user)):
    """获取系统当前配置（脱敏，需登录）"""
    return {"code": 200, "message": "success", "data": _current_config()}


@router.post("/config")
async def update_config(req: ConfigUpdate, current: User = Depends(get_current_user)):
    """更新系统配置（写入 .env 并热生效）"""
    env_path = Path(".env")
    updated = {}
    mappings = {
        "active_provider": "ACTIVE_LLM_PROVIDER",
        "amap_key": "AMAP_KEY",
        "llm_api_key": "LLM_API_KEY",
        "llm_api_base": "LLM_API_BASE",
        "llm_model": "LLM_MODEL",
        "embedding_model": "EMBEDDING_MODEL",
        "vision_provider": "VISION_PROVIDER",
        "vision_model": "VISION_MODEL",
        "asr_model": "ASR_MODEL",
        "tts_model": "TTS_MODEL",
        "amd_api_key": "AMD_API_KEY",
        "amd_api_base": "AMD_API_BASE",
        "amd_model": "AMD_MODEL",
        "ollama_api_base": "OLLAMA_API_BASE",
        "ollama_model": "OLLAMA_MODEL",
        "qwen3_8_flash_start": "QWEN3_8_FLASH_START",
        "qwen3_8_flash_end": "QWEN3_8_FLASH_END",
        "kb_chunk_size": "KB_CHUNK_SIZE",
        "kb_chunk_overlap": "KB_CHUNK_OVERLAP",
        "kb_top_k": "KB_TOP_K",
    }
    changed_config = False
    for field, env_key in mappings.items():
        val = getattr(req, field, None)
        if val is None:
            continue
        setattr(settings, env_key, val)
        if env_path.exists():
            dotenv.set_key(env_path, env_key, str(val))
        updated[field] = val
        changed_config = True

    # Agent 参数（仅内存态）
    agent_fields = ["orchestrator_temperature", "report_temperature", "max_agents"]
    for f in agent_fields:
        val = getattr(req, f, None)
        if val is not None:
            AGENT_CONFIG[f] = val
            updated[f] = val

    if changed_config:
        log_system_event("config", "更新配置: " + ", ".join(updated.keys()))
    return {"code": 200, "message": "success", "data": {"updated": updated, "config": _current_config()}}


@router.post("/test/db")
async def test_db(current: User = Depends(get_current_user)):
    """测试数据库连接"""
    from sqlalchemy import text
    from app.core.database import engine
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        log_system_event("datasource", "数据库连接测试成功: " + settings.DATABASE_URL.split("@")[-1])
        return {"code": 200, "message": "success", "data": {"ok": True, "detail": "数据库连接正常"}}
    except Exception as e:
        return {"code": 200, "message": "success", "data": {"ok": False, "detail": str(e)[:200]}}


@router.post("/test/llm")
async def test_llm(current: User = Depends(get_current_user)):
    """测试当前活跃提供商模型连接"""
    from app.core.llm import llm_available
    if not llm_available():
        provider = settings.ACTIVE_LLM_PROVIDER
        key_field = {"amd": "AMD_API_KEY", "ollama": "OLLAMA_API_BASE"}.get(provider, "LLM_API_KEY")
        return {"code": 200, "message": "success", "data": {"ok": False, "detail": f"未配置 {key_field}"}}
    from langchain_core.messages import HumanMessage
    llm = __import__("app.core.llm", fromlist=["get_llm"]).get_llm(temperature=0)
    if llm is None:
        provider = settings.ACTIVE_LLM_PROVIDER
        detail = (
            "Qwen3.8-Flash-Next 不在可用时间窗口内"
            if provider == "amd" and "Qwen3.8" in settings.AMD_MODEL and not is_qwen3_8_available()
            else "模型不可用"
        )
        return {"code": 200, "message": "success", "data": {"ok": False, "detail": detail}}
    try:
        resp = llm.invoke([HumanMessage(content="回复OK两个字")])
        text = resp.content if hasattr(resp, "content") else str(resp)
        active_model = {
            "amd": settings.AMD_MODEL,
            "ollama": settings.OLLAMA_MODEL,
        }.get(settings.ACTIVE_LLM_PROVIDER, settings.LLM_MODEL)
        log_system_event("model", f"模型连接测试成功: {active_model}（{settings.ACTIVE_LLM_PROVIDER}）")
        return {"code": 200, "message": "success", "data": {"ok": True, "detail": f"模型响应：{text[:50]}"}}
    except Exception as e:
        return {"code": 200, "message": "success", "data": {"ok": False, "detail": str(e)[:200]}}


@router.get("/llm/models")
async def list_llm_models(provider: str = "aliyun", current: User = Depends(get_current_user)):
    """
    获取 LLM 提供商可用模型列表（含百炼免费额度信息、模型分类、密钥概况）

    - 百炼：实时解析官方计费文档的免费额度目录（官方新增/调整自动跟随），
      并调用 /models 端点校验当前 Key 可用模型；
      文档抓取失败时回退内置静态目录。
    - AMD：实时抓取官方 tokenfactory 目录（免费/限时免费/付费自动标注）。
    控制台「账号免费额度剩余量/过期时间/状态」为账号级数据，
    由 /bailian/quota 端点配合用户 Cookie 实时获取（响应附控制台直达链接）。
    """
    if provider not in ("aliyun", "amd", "ollama"):
        provider = "aliyun"
    current_model = {
        "aliyun": settings.LLM_MODEL,
        "amd": settings.AMD_MODEL,
        "ollama": settings.OLLAMA_MODEL,
    }[provider]
    available = list_provider_models(provider)
    fetch_ok = bool(available)
    avail_set = set(available)

    def _row(mid: str, name: str, quota: str, validity: str, days: int, desc: str,
             category: str, is_free: bool, verified: bool, usage: str = ""):
        # 按分类匹配当前使用的模型（text→LLM / embedding→Embedding / vision→Vision / audio→ASR/TTS）
        if provider == "amd":
            # AMD：text→AMD_MODEL；vision→VISION_MODEL（仅当视觉提供商为 amd 时）
            if category == "vision":
                cur = settings.VISION_MODEL if settings.VISION_PROVIDER == "amd" else ""
            else:
                cur = settings.AMD_MODEL
        elif category == "audio":
            cur = settings.TTS_MODEL if usage == "tts" else settings.ASR_MODEL
        else:
            current_map = {
                "text": settings.LLM_MODEL,
                "embedding": settings.EMBEDDING_MODEL,
                "vision": settings.VISION_MODEL if settings.VISION_PROVIDER == "aliyun" else "",
                "multimodal": settings.VISION_MODEL if settings.VISION_PROVIDER == "aliyun" else "",
            }
            cur = current_map.get(category, settings.LLM_MODEL)
        return {
            "id": mid, "name": name, "free_quota": quota, "validity": validity, "days": days,
            "desc": desc, "category": category, "usage": usage,
            "category_name": MODEL_CATEGORIES.get(category, "其他"),
            "is_free": is_free, "verified": verified, "is_current": mid == cur,
        }

    def _guess_category(mid: str) -> str:
        """根据模型 ID 推断分类（用于 /models 返回中不在免费目录的模型）"""
        low = mid.lower()
        if "embedding" in low or "rerank" in low:
            return "embedding"
        if "omni" in low:
            return "multimodal"
        if any(k in low for k in ("tts", "asr", "audio", "paraformer", "cosyvoice", "sambert")):
            return "audio"
        if any(k in low for k in ("vl", "qvq", "-vision")):
            return "vision"
        return "text"

    def _usage_of(mid: str) -> str:
        """推断语音模型的用途（tts / asr），用于匹配当前 ASR/TTS 配置"""
        low = mid.lower()
        if any(k in low for k in ("tts", "cosyvoice", "sambert", "voice-enrollment", "voice-design")):
            return "tts"
        if any(k in low for k in ("asr", "paraformer", "transcription")):
            return "asr"
        return ""

    models = []
    if provider == "aliyun":
        # 1) 实时解析官方计费文档的免费额度目录（官方新增/调整自动跟随）
        directory = fetch_bailian_free_models()
        dir_ids = set()
        if directory:
            for m in directory:
                mid = m["model"]
                dir_ids.add(mid)
                models.append(_row(mid, mid, m["quota"], m["validity"], m["days"],
                                   f"{m['desc']}（官方免费额度目录）", m["category"], True,
                                   mid in avail_set, _usage_of(mid)))
        else:
            # 文档抓取/解析失败 → 回退内置静态目录
            dir_ids = set(BAILIAN_FREE_MODELS)
            for mid, info in BAILIAN_FREE_MODELS.items():
                models.append(_row(mid, info["name"], info["quota"], info["validity"], info["days"],
                                   info["desc"] + "（内置目录回退）", info["category"], True,
                                   mid in avail_set, info.get("usage", "")))
        # 2) /models 中存在但不在免费目录的模型（按规则自动分类）
        for mid in available:
            if mid in dir_ids:
                continue
            cat = _guess_category(mid)
            models.append(_row(mid, mid, "-", "-", 0, "其他可用模型（不在免费额度目录）",
                               cat, False, True))
        directory_ok = bool(directory)
    elif provider == "amd":
        # 实时抓取 AMD tokenfactory 官方目录（免费/限时免费/付费自动标注），失败时回退 /models 结果
        directory = fetch_amd_directory()
        dir_ids = set()
        for m in directory:
            dir_ids.add(m["id"])
            tier_name = AMD_TIER_NAMES.get(m["tier"], "未知")
            desc = m["desc"] + (f"（发布方: {m['publisher']}）" if m["publisher"] else "")
            row = _row(m["id"], m["name"], tier_name, "以控制台为准", 0,
                       desc, m["category"], m["tier"] != "paid", m["id"] in avail_set)
            row["tier"] = m["tier"]
            row["tier_name"] = tier_name
            row["vendor"] = m["publisher"]
            row["status"] = m.get("status", "")
            models.append(row)
        # /models 中存在但官方目录没有的模型（按规则自动分类）
        for mid in available:
            if mid in dir_ids:
                continue
            row = _row(mid, mid, "-", "以控制台为准", 0, "接口返回的其他模型（未在官方目录中）",
                       _guess_category(mid), False, True)
            row["tier"] = ""
            row["tier_name"] = "未知"
            models.append(row)
        directory_ok = bool(directory)
    else:
        for mid in available:
            models.append(_row(mid, mid, "-", "-", 0, "", _guess_category(mid), False, True))

    # 排序：AMD 按计费层级（免费 > 限时免费 > 付费）> 当前使用 > 已验证；
    # 其他提供商：有免费额度在前（有效期长者优先）> 无额度；组内 当前使用 > 已验证
    if provider == "amd":
        _tier_order = {"free": 0, "limited_free": 1, "paid": 2, "": 3}
        models.sort(key=lambda m: (
            _tier_order.get(m.get("tier", ""), 3),  # 免费优先，付费靠后
            not m["is_current"],                    # 当前使用优先
            not m["verified"],                       # 已验证优先
        ))
    else:
        models.sort(key=lambda m: (
            not m["is_free"],            # 免费额度优先
            -m["days"],                  # 有效期长优先
            not m["is_current"],         # 当前使用优先
            not m["verified"],           # 已验证优先
            m["category"] != "text",     # 大语言模型类内靠前
        ))

    # 密钥使用概况（脱敏；额度明细无公开 API，附控制台链接）
    if provider == "amd":
        console_urls = AMD_CONSOLE_URLS
        quota_note = ("模型目录实时抓取自 AMD 官方 tokenfactory 页面（免费/限时免费/付费自动标注）。"
                      "Dedicated 专属模型（付费）需消耗自有 Credits 部署实例，精确计费以 AMD 开发者控制台为准。")
    else:
        console_urls = BAILIAN_CONSOLE_URLS
        quota_note = ("阿里云未提供基于 DashScope API Key 的额度/余额查询公开接口，"
                      "精确剩余额度与到期时间请点击控制台链接查看（需阿里云账号登录）。")
    key_info = {
        "provider": provider,
        "provider_name": {"aliyun": "阿里云百炼", "amd": "AMD GPU Cloud", "ollama": "本地 Ollama"}.get(provider, provider),
        "api_key_masked": _mask(settings.LLM_API_KEY if provider == "aliyun" else (settings.AMD_API_KEY if provider == "amd" else "")),
        "api_key_configured": bool(settings.LLM_API_KEY if provider == "aliyun" else (settings.AMD_API_KEY if provider == "amd" else settings.OLLAMA_API_BASE)),
        "api_base": settings.LLM_API_BASE if provider == "aliyun" else (settings.AMD_API_BASE if provider == "amd" else settings.OLLAMA_API_BASE),
        "current_model": current_model,
        "embedding_model": settings.EMBEDDING_MODEL,
        "vision_provider": settings.VISION_PROVIDER,
        "vision_model": settings.VISION_MODEL,
        "asr_model": settings.ASR_MODEL,
        "tts_model": settings.TTS_MODEL,
        "available_count": len(available),
        "free_count": sum(1 for m in models if m["is_free"]),
        "console_urls": console_urls,
        "quota_note": quota_note,
        "qwen3_8_available": is_qwen3_8_available(),
        "directory_ok": bool(directory_ok) if provider in ("aliyun", "amd") else None,
    }

    log_system_event("model", f"拉取 {provider} 模型列表: /models 返回 {len(available)} 个")
    return {
        "code": 200, "message": "success",
        "data": {
            "provider": provider,
            "fetch_ok": fetch_ok,
            "available_count": len(available),
            "current_model": current_model,
            "categories": MODEL_CATEGORIES,
            "models": models,
            "key_info": key_info,
        },
    }


@router.get("/bailian/quota")
async def bailian_account_quota(current: User = Depends(get_current_user)):
    """
    百炼账号免费额度（静态内置快照，2026-09-02 从控制台同步）

    控制台「剩余量/过期时间/状态」为账号级登录态数据、无公开 API，
    按需求改为静态内置（app/core/bailian_quota_data.py）；
    额度变动时更新该文件即可。模型目录本身仍实时获取（官方计费文档）。
    """
    data = get_bailian_account_quota()
    return {"code": 200, "message": "success", "data": {"ok": True, **data}}


@router.get("/status")
async def system_status(current: User = Depends(get_current_user)):
    """系统运行状态总览"""
    db_ok = False
    try:
        from sqlalchemy import text
        from app.core.database import engine
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    from app.core.llm import llm_available
    active_model = settings.AMD_MODEL if settings.ACTIVE_LLM_PROVIDER == "amd" else settings.LLM_MODEL
    return {
        "code": 200,
        "message": "success",
        "data": {
            "version": settings.VERSION,
            "project": settings.PROJECT_NAME,
            "database": "connected" if db_ok else "disconnected",
            "llm_available": llm_available(),
            "llm_model": active_model,
            "llm_provider": settings.ACTIVE_LLM_PROVIDER,
            "embedding_model": settings.EMBEDDING_MODEL,
            "agents": [
                {"name": "Orchestrator", "framework": "LangGraph", "status": "ready"},
                {"name": "DataAgent", "framework": "LangChain Tool", "status": "ready"},
                {"name": "GisAgent", "framework": "Shapely/GeoPandas", "status": "ready"},
                {"name": "ReportAgent", "framework": "LangChain LLM", "status": "ready"},
                {"name": "RagAgent", "framework": "LangChain RAG", "status": "ready"},
            ],
        },
    }


@router.get("/logs")
async def system_logs(limit: int = 100, current: User = Depends(get_current_user)):
    """获取系统日志"""
    _SYSTEM_LOGS.insert(0, {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "level": "INFO",
        "source": "system",
        "message": "日志接口被访问",
    })
    logs = _SYSTEM_LOGS[:limit]
    return {"code": 200, "message": "success", "data": logs}


# ====== 用户权限管理（仅管理员） ======

@router.get("/users")
async def list_users(
    current: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """获取用户列表（仅管理员）"""
    users = db.query(User).order_by(User.id).all()
    return {
        "code": 200,
        "message": "success",
        "data": [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "role": u.role,
                "created_at": u.created_at.strftime("%Y-%m-%d %H:%M:%S") if u.created_at else "",
            }
            for u in users
        ],
    }


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    req: RoleUpdate,
    current: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """修改用户角色（仅管理员；不能修改自己的角色）"""
    if req.role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="角色只能是 user 或 admin")
    if user_id == current.id:
        raise HTTPException(status_code=400, detail="不能修改自己的角色")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.role = req.role
    db.commit()
    log_system_event("admin", f"用户 {user.username} 角色已变更为 {req.role}（操作人: {current.username}）")
    return {"code": 200, "message": "success", "data": {"id": user.id, "role": user.role}}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """删除用户（仅管理员；不能删除自己）"""
    if user_id == current.id:
        raise HTTPException(status_code=400, detail="不能删除自己的账号")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    db.delete(user)
    db.commit()
    log_system_event("admin", f"用户 {user.username} 已被删除（操作人: {current.username}）")
    return {"code": 200, "message": "success", "data": {"id": user_id}}