FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system --gid 10001 kylot \
    && useradd --system --uid 10001 --gid kylot --home-dir /nonexistent kylot

COPY backend/requirements-core.txt /tmp/requirements-core.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install --requirement /tmp/requirements-core.txt

COPY --chown=kylot:kylot backend /app/backend

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

CMD ["python", "-m", "uvicorn", "backend.server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
