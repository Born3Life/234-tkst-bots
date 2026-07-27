FROM python:3.11-slim

WORKDIR /app

COPY SMR/pyproject.toml ./
RUN pip install uv && uv sync

COPY SMR/ .

CMD ["uv", "run", "python", "-m", "bot"]
