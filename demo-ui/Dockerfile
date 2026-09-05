FROM ghcr.io/astral-sh/uv:0.10.11 AS uv
FROM python:3.12.12-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /workspace
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY demo-ui/ ./
RUN useradd --create-home app
USER app
EXPOSE 8501
CMD ["/workspace/.venv/bin/streamlit", "run", "app.py", "--server.address=0.0.0.0", "--browser.gatherUsageStats=false"]
