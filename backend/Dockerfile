# StudyRoute sandbox API. Build from the repository root:
#   docker build -f backend/Dockerfile -t studyroute-api .
# docker compose does this for you (see docker-compose.yml).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATA_DIR=/srv/data \
    RULES_FILE=/srv/config/rules.yaml \
    BANK_NETWORK_FILE=/srv/config/bank_network.yaml

WORKDIR /srv
RUN useradd --system --uid 10001 --home-dir /srv --shell /usr/sbin/nologin studyroute \
    && mkdir -p /srv/data && chown studyroute /srv/data

COPY backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY backend/app ./app
COPY config ./config
COPY backend/docker-entrypoint.sh ./docker-entrypoint.sh

USER studyroute
VOLUME ["/srv/data"]
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
ENTRYPOINT ["sh", "/srv/docker-entrypoint.sh"]
