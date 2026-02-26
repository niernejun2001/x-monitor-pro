FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Shanghai

# 1️⃣ 安装 Chromium + 运行依赖
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    fonts-noto-cjk \
    fonts-liberation \
    libnss3 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libasound2 \
    libgbm1 \
    libxshmfence1 \
    libu2f-udev \
    libvulkan1 \
    ca-certificates \
    curl \
    wget \
    procps \
    && rm -rf /var/lib/apt/lists/*

# 2️⃣ Chromium 路径（给 DrissionPage 用）
ENV CHROME_PATH=/usr/bin/chromium
ENV CHROMIUM_PATH=/usr/bin/chromium

WORKDIR /app

# 3️⃣ Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4️⃣ 复制代码
COPY app.py .
COPY templates/ ./templates/

# 5️⃣ 状态文件目录（用于 volume）
RUN mkdir -p /app/data

# 6️⃣ Flask 端口
EXPOSE 5000

CMD ["python", "app.py"]
