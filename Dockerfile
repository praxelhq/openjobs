FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY openjobs ./openjobs
COPY examples ./examples
COPY scripts ./scripts
RUN pip install --no-cache-dir uv==0.9.26 && uv sync --locked --no-dev
RUN groupadd --gid 10001 openjobs \
    && useradd --create-home --uid 10001 --gid 10001 openjobs \
    && mkdir -p /app/data \
    && chown openjobs:openjobs /app/data
ENV PATH="/app/.venv/bin:$PATH" \
    OPENJOBS_DB="/app/data/jobs.sqlite" \
    PYTHONDONTWRITEBYTECODE="1" \
    PYTHONUNBUFFERED="1"
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/health', timeout=2)" || exit 1
CMD ["uvicorn", "openjobs.api:app", "--host", "0.0.0.0", "--port", "8000"]
