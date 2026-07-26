FROM python:3.11-slim

WORKDIR /app

COPY "учет и контроль/pyproject.toml" "учет и контроль/uv.lock" ./
RUN pip install uv && uv sync --frozen

COPY "учет и контроль/" .

CMD ["uv", "run", "python", "-m", "bot"]
