FROM python:3.11-slim

RUN apt-get update -qq && apt-get install -y -qq libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
RUN pip install uv && uv sync

COPY . .

CMD ["uv", "run", "python", "-m", "bot"]
