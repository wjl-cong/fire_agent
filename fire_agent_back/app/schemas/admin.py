"""
系统管理 Schema
"""
from typing import Optional
from pydantic import BaseModel


class ConfigUpdate(BaseModel):
    """配置更新请求（仅更新非空字段）"""
    # 活跃提供商切换
    active_provider: Optional[str] = None  # aliyun | amd | ollama | longcat

    # 阿里百炼 / 通用 OpenAI 兼容
    amap_key: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_api_base: Optional[str] = None
    llm_model: Optional[str] = None
    embedding_model: Optional[str] = None

    # 视觉 / 语音模型（视觉可切换 aliyun/amd，语音恒定阿里百炼）
    vision_provider: Optional[str] = None  # aliyun | amd
    vision_model: Optional[str] = None
    asr_model: Optional[str] = None
    tts_model: Optional[str] = None

    # AMD GPU Cloud
    amd_api_key: Optional[str] = None
    amd_api_base: Optional[str] = None
    amd_model: Optional[str] = None

    # 本地 Ollama（无需 API Key）
    ollama_api_base: Optional[str] = None
    ollama_model: Optional[str] = None

    # LongCat（兼容 OpenAI 格式，仅 LLM）
    longcat_api_key: Optional[str] = None
    longcat_api_base: Optional[str] = None
    longcat_model: Optional[str] = None

    # Qwen3.8-Flash-Next 时间窗口
    qwen3_8_flash_start: Optional[str] = None
    qwen3_8_flash_end: Optional[str] = None

    # 知识库参数
    kb_chunk_size: Optional[int] = None
    kb_chunk_overlap: Optional[int] = None
    kb_top_k: Optional[int] = None

    # Rerank 精排（P1）
    rerank_enabled: Optional[bool] = None
    rerank_model: Optional[str] = None

    # 流式输出（P2#18）
    llm_stream_enabled: Optional[bool] = None

    # Agent 参数
    orchestrator_temperature: Optional[float] = None
    report_temperature: Optional[float] = None
    max_agents: Optional[int] = None
    agent_require_approval: Optional[bool] = None  # HITL：报告生成后需人工审批


class RoleUpdate(BaseModel):
    """用户角色更新请求"""
    role: str  # user / admin