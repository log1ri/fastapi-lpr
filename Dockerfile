FROM python:3.11-slim

# Runtime env
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

# System deps for opencv-python-headless on slim (avoid libGL/libgthread errors)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libgl1 \
  && rm -rf /var/lib/apt/lists/*

# Copy uv binaries (pinned)
COPY --from=ghcr.io/astral-sh/uv:0.9.18 /uv /uvx /bin/


# ---- Dependencies layer (best cache) ----
# Use bind mounts for lock+pyproject (requires BuildKit)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=/app/uv.lock \
    --mount=type=bind,source=pyproject.toml,target=/app/pyproject.toml \
    uv sync --locked --no-install-project

# ---- Copy application code ----
COPY . /app

# Install project (and any editable/local deps) into venv
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

EXPOSE 8000

# Run app
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]