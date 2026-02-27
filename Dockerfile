FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    XMONITOR_PORT=5000 \
    XMONITOR_PERSIST_BROWSER_PROFILE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    psmisc \
    fonts-noto-cjk \
    tzdata \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

COPY app.py /app/app.py
COPY templates /app/templates

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:5000/api/state', timeout=4); sys.exit(0)"

CMD ["python", "-u", "app.py"]
