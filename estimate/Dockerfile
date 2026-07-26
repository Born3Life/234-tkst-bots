FROM python:3.11-slim

WORKDIR /app

COPY estimate/pyproject.toml estimate/uv.lock ./
RUN pip install uv && uv sync --frozen

COPY estimate/ .

CMD ["uv", "run", "python", "-m", "bot"]
