# 焰哨多Agent与可视化平台 · 后端镜像（P2#16 Docker 化交付）
# 构建：docker build -t fire-agent-backend .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

# 系统依赖：libgl1/libglib2.0-0 为 opencv 运行所需；curl 供健康检查
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖（利用层缓存）
COPY requirements.txt .
RUN pip install -r requirements.txt

# 再拷贝代码
COPY . .

# 运行期持久化目录（知识库上传 / 视觉图片）由 compose 挂载卷提供
RUN mkdir -p data/knowledge_base data/vision_uploads

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
