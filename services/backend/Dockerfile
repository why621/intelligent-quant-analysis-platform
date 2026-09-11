FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    QUANT_DATA_DIR=/app/data/processed \
    BACKTEST_DB_PATH=/app/var/backtests.db

WORKDIR /app

COPY services/algorithms /tmp/algorithms
COPY services/backend /tmp/backend
RUN pip install --no-cache-dir /tmp/algorithms /tmp/backend \
    && rm -rf /tmp/algorithms /tmp/backend

RUN groupadd --system quant \
    && useradd --system --gid quant --home-dir /app quant \
    && mkdir -p /app/data/processed /app/var \
    && chown -R quant:quant /app

USER quant
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)" || exit 1

CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers ${GUNICORN_WORKERS:-2} --threads ${GUNICORN_THREADS:-2} --timeout ${GUNICORN_TIMEOUT:-120} app.wsgi:app"]
