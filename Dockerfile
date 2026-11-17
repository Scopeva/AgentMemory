FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY cli ./cli

RUN pip install --no-cache-dir .

# Default data directory; override with a volume for persistence.
ENV AGENT_MEMORY_CONFIG_PATH=/app/config.example.toml \
    AGENT_MEMORY_DATABASE_PATH=/data/memory.db \
    PYTHONPATH=/app/src:/app/cli

# sqlite-vec: point at the shared object to enable hybrid vector search.
# Without it the service runs in lexical-only mode.
# ENV SQLITE_VEC_PATH=/usr/local/lib/sqlite-vec/vec0.so

VOLUME /data

EXPOSE 8765

# Use the interpreter that actually has the packages installed.
# pip installs into /usr/local/lib/python3.11/site-packages/ (system python),
# not the venv the base image may have pre-baked.
CMD ["python3", "-m", "agent_memory.main"]

# Keep the container running for interactive use (docker compose exec / attach).
# Use `docker compose exec agent-memory python -m memoryctl ...` for one-shot commands.
