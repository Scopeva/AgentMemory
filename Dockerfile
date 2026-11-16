FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir .

# Default data directory; override with a volume for persistence.
ENV AGENT_MEMORY_CONFIG_PATH=/app/config.example.toml \
    AGENT_MEMORY_DATABASE_PATH=/data/memory.db

VOLUME /data

EXPOSE 8765

CMD ["python", "-m", "agent_memory.main"]
