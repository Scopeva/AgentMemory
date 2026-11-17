FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY cli ./cli

RUN pip install --no-cache-dir .

# Default data directory; override with a volume for persistence.
ENV AGENT_MEMORY_CONFIG_PATH=/app/config.example.toml \
    AGENT_MEMORY_DATABASE_PATH=/data/memory.db

# sqlite-vec: point at the shared object to enable hybrid vector search.
# Without it the service runs in lexical-only mode.
# ENV SQLITE_VEC_PATH=/usr/local/lib/sqlite-vec/vec0.so

VOLUME /data

EXPOSE 8765

CMD ["python", "-m", "agent_memory.main"]
