FROM python:3.12-slim
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
RUN pip install -U pip
COPY pyproject.toml /app/
WORKDIR /app
RUN pip install .
RUN pip install "git+https://github.com/gagarinyury/aiogram_bot_template@v1.2.0"
COPY runtime /app/runtime
COPY migrations /app/migrations
CMD ["uvicorn", "runtime.main:app", "--host", "0.0.0.0", "--port", "8000"]