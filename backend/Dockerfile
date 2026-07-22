# Python 3.11/3.12 Slim Image (Stable & Lightweight)
FROM python:3.11-slim

# Set Working Directory
WORKDIR /app

# Environment Variables
ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1

# Install System Dependencies (Alembic & SQLite/Postgres support ke liye)
RUN apt-get update && apt-get install -y --no-install-recommends \
  build-essential \
  && rm -rf /var/lib/apt/lists/*

# Install Python Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Project Files
COPY . .

# Expose FastAPI Port
EXPOSE 8000

# Run FastAPI Server (main.py)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]