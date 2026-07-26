FROM python:3.11-slim

WORKDIR /app

COPY "accounting and control/pyproject.toml" "accounting and control/uv.lock" ./
RUN pip install uv && uv sync --frozen

COPY "accounting and control/" .

CMD ["uv", "run", "python", "-m", "bot"]
