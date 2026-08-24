# =============================================================================
# ULPF - Universal Log Pre-processing Framework (air-gapped container image)
#
# BUILD (from project directory containing Dockerfile):
#   docker build -t ulpf:latest .
#
# RUN standalone:
#   docker run --rm -p 8501:8501 -v $(pwd)/lake:/app/lake ulpf:latest
#
# Or with Compose:
#   docker compose up --build
#
# App will be available at http://localhost:8501
# The ./lake volume mount persists the Parquet lake across container runs.
# =============================================================================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py lake.py ./

# Pre-create the lake directory so volume mounts bind cleanly
RUN mkdir -p /app/lake

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
