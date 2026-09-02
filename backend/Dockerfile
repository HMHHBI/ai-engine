# Python 3.11 Slim Image
FROM python:3.11-slim

# Set Working Directory
WORKDIR /app

# Environment Variables
ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1

# Upgrade pip for fast parallel binary wheels support
RUN pip install --no-cache-dir --upgrade pip

# Install Python Dependencies (Using pre-built binary wheels)
COPY requirements.txt .
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# Copy Project Files
COPY . .

# Expose FastAPI Port
EXPOSE 8000

# Run FastAPI Server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]