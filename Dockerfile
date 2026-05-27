FROM python:3.11-slim

# System deps (needed for pandas/numpy C extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY pyproject.toml ./
COPY backend/ ./backend/

# Install Python dependencies
RUN pip install --no-cache-dir -e ".[api]"

# Port the FastAPI server listens on
EXPOSE 8765

# Run with uvicorn — single worker is fine for 1-core VPS
CMD ["uvicorn", "backend.api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8765", \
     "--workers", "1"]
