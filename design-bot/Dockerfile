FROM python:3.11-slim

WORKDIR /app

COPY design-bot/pyproject.toml design-bot/uv.lock ./
RUN pip install uv && uv sync --frozen

COPY design-bot/ .

CMD ["uv", "run", "python", "-m", "bot"]
