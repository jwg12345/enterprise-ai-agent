FROM ghcr.io/astral-sh/uv:0.10.11 AS uv
FROM python:3.12.12-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /workspace
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY ai-service/requirements-m2.lock ./
RUN uv pip install --python /workspace/.venv/bin/python --torch-backend cpu --require-hashes -r requirements-m2.lock
COPY ai-service/requirements-m3.lock ./
RUN uv pip install --python /workspace/.venv/bin/python --require-hashes -r requirements-m3.lock
COPY ai-service/app ./app
RUN useradd --create-home app && mkdir -p /model-cache /index && chown app /model-cache /index
USER app
EXPOSE 8000
CMD ["/workspace/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
