FROM python:3.11-slim

WORKDIR /app

COPY проектирование\ зданий/pyproject.toml проектирование\ зданий/uv.lock ./
RUN pip install uv && uv sync --frozen

COPY проектирование\ зданий/ .

CMD ["uv", "run", "python", "-m", "bot"]
