FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖（包括 Node.js 20.x、OpenCLI、Chromium）
# Docker 层缓存：此层仅在 apt 依赖变更时重建，日常 --build 秒过
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    ca-certificates \
    postgresql-client \
    chromium \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm config set registry https://registry.npmmirror.com \
    && npm install -g @jackwener/opencli \
    && rm -rf /var/lib/apt/lists/*

# Chromium Docker wrapper：拦截所有 chrome 调用，注入 --no-sandbox（独立层，改脚本不触发 apt 重下载）
RUN printf '#!/bin/sh\nexec /usr/bin/chromium --no-sandbox --disable-gpu "$@"\n' > /usr/bin/google-chrome \
    && chmod +x /usr/bin/google-chrome

# 共享 CDP 端点（opencli browser 连接此端口）
ENV OPENCLI_CDP_ENDPOINT=http://127.0.0.1:9222

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 创建数据目录
RUN mkdir -p /app/data/agents /app/data/groups /app/data/attachments /app/uploads

COPY . .

EXPOSE 8000
