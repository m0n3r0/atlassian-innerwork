FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    INNERWORK_DATABASE_URL=sqlite:////tmp/innerwork/innerwork.db

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY data ./data
COPY spec ./spec
COPY examples ./examples
COPY docs ./docs

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).read()"

CMD ["python", "-m", "uvicorn", "innerwork.app:app", "--host", "0.0.0.0", "--port", "8000"]
