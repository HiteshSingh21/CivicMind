FROM python:3.12-slim

WORKDIR /app

# Prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies if needed (e.g., for certain wheel compilations)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application layers
COPY ./agents ./agents
COPY ./api ./api
COPY ./data ./data
COPY ./frontend ./frontend

EXPOSE 8080

# Run uvicorn on 8080 (Cloud Run default expects port 8080)
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
