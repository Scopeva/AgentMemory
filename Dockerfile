FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY config.example.toml ./
COPY src ./src
COPY cli ./cli
COPY web ./web

# Install the agent_memory package (and register it in site-packages).
RUN pip install --no-cache-dir .

# Make in-container `python3 -m memoryctl` and `python3 -m agent_memory...`
# work without depending on the pip-installed copy: point PYTHONPATH at the
# repo layout so the *latest* source is always what runs. This also fixes
# stale-site-packages bugs (e.g. browsing.py calling a repository function
# that only exists in newer src/ revisions).
ENV AGENT_MEMORY_CONFIG_PATH=/app/config.example.toml \
    AGENT_MEMORY_DATABASE_PATH=/data/memory.db \
    PYTHONPATH=/app/src:/app/cli

# sqlite-vec: point at the shared object to enable hybrid vector search.
# Without it the service runs in lexical-only mode.
# ENV SQLITE_VEC_PATH=/usr/local/lib/sqlite-vec/vec0.so

VOLUME /data

EXPOSE 8765

# Use python3 (system interpreter). PYTHONPATH puts /app/src first so the
# in-repo source always wins over any pip-installed copy.
CMD ["python3", "-m", "agent_memory.main"]

# Keep the container running for interactive use (docker compose exec / attach).
# Use `docker compose exec agent-memory python3 -m memoryctl ...` for one-shot commands.
