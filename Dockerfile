FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv==0.11.19 \
    && uv sync --frozen --no-dev

COPY . /app

CMD ["python", "scripts/s11_runtime_server.py"]
