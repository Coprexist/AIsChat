FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖（包括 Node.js 20.x 和 OpenCLI）
# 使用清华镜像源加速 apt 下载
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    ca-certificates \
    postgresql-client \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    # npm 镜像源加速
    && npm config set registry https://registry.npmmirror.com \
    && npm install -g @jackwener/opencli \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 创建数据目录
RUN mkdir -p /app/data/agents /app/data/groups /app/data/attachments /app/uploads

COPY . .

EXPOSE 8000
