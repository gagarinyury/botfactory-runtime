FROM python:3.11-slim
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
RUN pip install --upgrade pip wheel setuptools
COPY pyproject.toml /app/
WORKDIR /app
RUN pip install .
RUN pip install "aiogram==3.22.0" "aiohttp==3.12.15" "redis==6.4.0" "pydantic==2.11.9" "prometheus-client" "structlog" "cachetools"
# RUN pip install --no-deps "git+https://github.com/gagarinyury/aiogram_bot_template@v1.2.0"
COPY runtime /app/runtime
COPY migrations /app/migrations
COPY tests /app/tests
CMD ["uvicorn", "runtime.main:app", "--host", "0.0.0.0", "--port", "8000"]