# ============================================================
# 多阶段构建 - Stage 1: 依赖安装
# ============================================================
FROM python:3.11-slim AS builder

WORKDIR /build

# 安装编译依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libgl1-mesa-glx libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============================================================
# 多阶段构建 - Stage 2: 运行时镜像
# ============================================================
FROM python:3.11-slim

LABEL maintainer="safecam" \
      description="SafeCam 智能安防监控系统" \
      version="2.0"

WORKDIR /app

# 仅安装运行时系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev curl \
    && rm -rf /var/lib/apt/lists/*

# 从 builder 阶段复制已安装的 Python 包
COPY --from=builder /install /usr/local

# 复制应用代码
COPY backend/ backend/
COPY frontend/ frontend/
COPY models/ models/
COPY alembic/ alembic/
COPY alembic.ini .
COPY config.yaml .
COPY scripts/ scripts/

# 创建非 root 用户运行应用
RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && mkdir -p /app/data/screenshots /app/logs \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
