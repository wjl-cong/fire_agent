"""
全局配置 — 从环境变量 / .env 读取
"""
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 项目基本信息
    PROJECT_NAME: str = "焰哨多Agent与可视化平台"
    VERSION: str = "1.0.0"

    # 报告署名信息（自动追加到生成的每份分析报告末尾）
    REPORT_FOOTER: str = (
        "\n\n---\n\n"
        "> **系统与开发者信息**\n"
        "> - 系统名称：焰哨多Agent与可视化平台\n"
        "> - 开发者：wjl\n"
        "> - 联系邮箱：19136220923@163.com\n"
        "> - 后端源码：https://gitee.com/wjl2004/fire_agent_back\n"
        "> - 前端源码：https://gitee.com/wjl2004/fire_agent_front\n"
        "> - 在线演示：https://wjl2004.ffuf.cn/\n"
        "> - GitHub 仓库：https://github.com/wjl-cong/fire_agent (⭐ Star welcome!)\n"
    )

    # JWT 认证（由 .env 提供，避免硬编码）
    JWT_SECRET: str = "fire-agent-platform-secret-key-change-in-prod"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 小时

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:4173"]

    # 数据库
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/fire_agent"

    # 高德地图 Key
    AMAP_KEY: str = ""

    # 活跃 LLM 提供商（aliyun | amd | ollama）
    ACTIVE_LLM_PROVIDER: str = "aliyun"

    # 模型 API — 阿里百炼（兼容 OpenAI 格式）
    LLM_API_KEY: str = ""
    LLM_API_BASE: str = ""
    LLM_MODEL: str = "qwen-plus"
    EMBEDDING_MODEL: str = "text-embedding-v3"
    # 视觉 / 语音模型（恒定阿里百炼，独立于 ACTIVE_LLM_PROVIDER）
    VISION_MODEL: str = "qwen-vl-plus"
    ASR_MODEL: str = "qwen3-asr-flash"
    TTS_MODEL: str = "qwen3-tts-flash"

    # 模型 API — AMD GPU Cloud（兼容 OpenAI 格式）
    AMD_API_KEY: str = ""
    AMD_API_BASE: str = "https://developer.amd.com.cn/radeon/v1"
    AMD_MODEL: str = "DeepSeek-V4-Flash"

    # 模型 API — 本地 Ollama（兼容 OpenAI 格式，无需 API Key）
    OLLAMA_API_BASE: str = "http://localhost:11434/v1"
    OLLAMA_MODEL: str = "qwen2.5:7b"

    # Qwen3.8-Flash-Next 可用时间窗口（空表示不限）
    QWEN3_8_FLASH_START: str = ""
    QWEN3_8_FLASH_END: str = ""

    # RAG 知识库
    KB_UPLOAD_DIR: str = "data/knowledge_base"
    KB_CHUNK_SIZE: int = 500
    KB_CHUNK_OVERLAP: int = 50
    KB_TOP_K: int = 5

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()