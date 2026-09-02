"""
LangChain LLM & Embedding 客户端 — 多提供商支持

支持的提供商:
  - aliyun:  阿里百炼 / 任意 OpenAI 兼容 API
  - amd:     AMD GPU Cloud（OpenAI 兼容格式）
  - ollama:  本地 Ollama（OpenAI 兼容格式，无需 API Key）
"""
from datetime import datetime
import base64

import httpx
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.core.config import settings


# ===================== 提供商路由 =====================

def get_llm(**kwargs) -> ChatOpenAI | None:
    """
    获取 LLM 实例（根据活跃提供商自动路由）

    Args:
        **kwargs: 可传入 model, temperature, max_tokens 覆盖默认值
    """
    provider = settings.ACTIVE_LLM_PROVIDER
    if provider == "amd":
        return _get_amd_llm(**kwargs)
    if provider == "ollama":
        return _get_ollama_llm(**kwargs)
    return _get_aliyun_llm(**kwargs)


def get_embedding() -> OpenAIEmbeddings | None:
    """获取 Embedding 实例（固定走阿里百炼 — AMD GPU Cloud 不提供 Embedding 模型）"""
    if not settings.LLM_API_KEY:
        return None
    return OpenAIEmbeddings(
        model=settings.EMBEDDING_MODEL,
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_API_BASE or None,
    )


# ===================== 视觉 / 语音（恒定阿里百炼） =====================

def _bailian_base() -> str:
    """阿里百炼 OpenAI 兼容端点"""
    return (settings.LLM_API_BASE or "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/")


def get_vision_llm(**kwargs) -> ChatOpenAI | None:
    """视觉理解模型实例（按 VISION_PROVIDER 路由：aliyun 百炼 / amd GPU Cloud）"""
    if settings.VISION_PROVIDER == "amd":
        if not settings.AMD_API_KEY or not settings.VISION_MODEL:
            return None
        return ChatOpenAI(
            model=kwargs.get("model", settings.VISION_MODEL),
            api_key=settings.AMD_API_KEY,
            base_url=settings.AMD_API_BASE or "https://developer.amd.com.cn/radeon/v1",
            temperature=kwargs.get("temperature", 0.1),
            max_tokens=kwargs.get("max_tokens", 2048),
        )
    # 默认阿里百炼
    if not settings.LLM_API_KEY:
        return None
    return ChatOpenAI(
        model=kwargs.get("model", settings.VISION_MODEL),
        api_key=settings.LLM_API_KEY,
        base_url=_bailian_base(),
        temperature=kwargs.get("temperature", 0.1),
        max_tokens=kwargs.get("max_tokens", 2048),
    )


def vision_available() -> bool:
    """视觉模型是否可用"""
    if settings.VISION_PROVIDER == "amd":
        return bool(settings.AMD_API_KEY and settings.VISION_MODEL)
    return bool(settings.LLM_API_KEY and settings.VISION_MODEL)


def transcribe_audio(file_bytes: bytes, filename: str) -> str:
    """
    语音识别（ASR）：音频字节 → 文本

    走百炼 OpenAI 兼容 /chat/completions 端点 + input_audio（data URI）格式，
    模型: ASR_MODEL（qwen3-asr-flash / paraformer-v2）。音频需为 wav/mp3 格式。
    返回识别文本；失败抛出异常。
    """
    if not settings.LLM_API_KEY:
        raise RuntimeError("未配置 LLM_API_KEY，语音识别不可用")
    # 推断音频 mime（前端已转为 wav）
    ext = (filename or "").rsplit(".", 1)[-1].lower()
    mime = {"wav": "wav", "mp3": "mp3", "opus": "opus", "aac": "aac", "amr": "amr"}.get(ext, "wav")
    b64 = base64.b64encode(file_bytes).decode()
    resp = httpx.post(
        f"{_bailian_base()}/chat/completions",
        headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
        json={
            "model": settings.ASR_MODEL,
            "messages": [{
                "role": "user",
                "content": [{
                    "type": "input_audio",
                    "input_audio": {"data": f"data:audio/{mime};base64,{b64}", "format": mime},
                }],
            }],
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("choices", [{}])[0].get("message", {}).get("content", "")


def synthesize_speech(text: str) -> bytes:
    """
    语音合成（TTS）：文本 → 音频字节（wav）

    走百炼原生 /api/v1/services/aigc/multimodal-generation/generation 端点，
    模型: TTS_MODEL（qwen3-tts-flash / qwen-tts 系列），返回 output.audio.url 再下载。
    返回音频二进制；失败抛出异常。
    """
    if not settings.LLM_API_KEY:
        raise RuntimeError("未配置 LLM_API_KEY，语音合成不可用")
    # 原生端点：https://dashscope.aliyuncs.com/api/v1/...
    native_base = "https://dashscope.aliyuncs.com/api/v1"
    resp = httpx.post(
        f"{native_base}/services/aigc/multimodal-generation/generation",
        headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
        json={"model": settings.TTS_MODEL, "input": {"text": text[:500], "voice": "Cherry"}},
        timeout=120,
    )
    resp.raise_for_status()
    audio = resp.json().get("output", {}).get("audio", {})
    url = audio.get("url")
    if not url:
        raise RuntimeError("语音合成未返回音频 URL")
    audio_resp = httpx.get(url, timeout=60)
    audio_resp.raise_for_status()
    return audio_resp.content


def llm_available() -> bool:
    """检查当前活跃的 LLM 提供商是否可用"""
    provider = settings.ACTIVE_LLM_PROVIDER
    if provider == "amd":
        return bool(settings.AMD_API_KEY)
    if provider == "ollama":
        return bool(settings.OLLAMA_API_BASE)  # 本地 Ollama 无需 API Key
    return bool(settings.LLM_API_KEY)


def list_provider_models(provider: str | None = None) -> list[str]:
    """
    获取指定提供商可用模型列表（调用 OpenAI 兼容 /models 端点）

    返回模型 id 列表；Key 未配置或请求失败时返回空列表。
    """
    provider = provider or settings.ACTIVE_LLM_PROVIDER
    if provider == "amd":
        base = settings.AMD_API_BASE or "https://developer.amd.com.cn/radeon/v1"
        key = settings.AMD_API_KEY
        if not key:
            return []
    elif provider == "ollama":
        base = settings.OLLAMA_API_BASE
        key = "ollama"  # Ollama 不校验 Key
        if not base:
            return []
    else:  # aliyun
        base = settings.LLM_API_BASE or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        key = settings.LLM_API_KEY
        if not key:
            return []
    try:
        resp = httpx.get(
            f"{base.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return [m.get("id") for m in data if m.get("id")]
    except Exception:
        return []


# ===================== 阿里云 / 通用 OpenAI 兼容 =====================

def _get_aliyun_llm(**kwargs) -> ChatOpenAI | None:
    """阿里百炼 LLM 实例"""
    if not settings.LLM_API_KEY:
        return None
    return ChatOpenAI(
        model=kwargs.get("model", settings.LLM_MODEL),
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_API_BASE or None,
        temperature=kwargs.get("temperature", 0.1),
        max_tokens=kwargs.get("max_tokens", 2048),
    )


# ===================== AMD GPU Cloud =====================

def _get_amd_llm(**kwargs) -> ChatOpenAI | None:
    """AMD GPU Cloud LLM 实例（含 Qwen3.8-Flash-Next 时间窗口校验）"""
    if not settings.AMD_API_KEY:
        return None
    # 模型选择：优先使用 kwargs 参数，否则使用配置的默认模型
    model = kwargs.get("model", settings.AMD_MODEL or "DeepSeek-V4-Flash")
    # Qwen3.8-Flash 系列免费模型需时间窗口校验（Qwen3.8-27B 等付费专属模型不受限）
    if "qwen3.8-flash" in model.lower():
        if not is_qwen3_8_available():
            return None  # 不在可用窗口内，返回 None 触发降级
    return ChatOpenAI(
        model=model,
        api_key=settings.AMD_API_KEY,
        base_url=settings.AMD_API_BASE or "https://developer.amd.com.cn/radeon/v1",
        temperature=kwargs.get("temperature", 0.1),
        max_tokens=kwargs.get("max_tokens", 2048),
    )


# ===================== 本地 Ollama =====================

def _get_ollama_llm(**kwargs) -> ChatOpenAI | None:
    """本地 Ollama LLM 实例（OpenAI 兼容接口，无需 API Key）"""
    if not settings.OLLAMA_API_BASE:
        return None
    return ChatOpenAI(
        model=kwargs.get("model", settings.OLLAMA_MODEL),
        api_key="ollama",  # Ollama 不校验 Key，但 SDK 要求非空
        base_url=settings.OLLAMA_API_BASE,
        temperature=kwargs.get("temperature", 0.1),
        max_tokens=kwargs.get("max_tokens", 2048),
    )


def is_qwen3_8_available() -> bool:
    """
    检查 Qwen3.8-Flash-Next 模型是否在可用时间窗口内
    
    配置 QWEN3_8_FLASH_START / QWEN3_8_FLASH_END 定义时间窗口。
    若两个字段均为空，则视为始终可用。
    格式: "YYYY-MM-DD HH:MM:SS"
    """
    start_str = settings.QWEN3_8_FLASH_START
    end_str = settings.QWEN3_8_FLASH_END
    if not start_str or not end_str:
        return True  # 未配置时间窗口，视为可用
    try:
        now = datetime.now()
        start = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
        end = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S")
        return start <= now <= end
    except (ValueError, TypeError):
        return True  # 格式解析错误，保守视为可用