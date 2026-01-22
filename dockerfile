FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=main.py

# Install system dependencies including Node.js for JavaScript execution
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    nodejs \
    npm \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirement.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirement.txt

# Copy project files
COPY . .

# Expose port
EXPOSE 5000

# Create startup script that runs both Gunicorn and Celery worker
RUN echo '#!/bin/bash\n\
celery -A celery_worker.celery worker --loglevel=info --pool=solo --detach\n\
exec gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 2 --timeout 120 --access-logfile - --error-logfile - main:app\n\
' > /app/start.sh && chmod +x /app/start.sh

CMD ["/app/start.sh"]