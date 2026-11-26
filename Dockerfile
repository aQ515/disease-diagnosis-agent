# 医疗 AI 导诊助手 API 镜像
FROM python:3.13-slim

WORKDIR /app

# 系统依赖（py2neo / sentence-transformers 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-web.txt requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -r requirements-web.txt \
    && pip install --no-cache-dir -r requirements-api.txt

COPY . .

EXPOSE 8002

CMD ["python", "-m", "uvicorn", "fastapi_app.main:app", "--host", "0.0.0.0", "--port", "8002"]
