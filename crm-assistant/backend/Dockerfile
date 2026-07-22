FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create uploads directory
RUN mkdir -p /app/uploads

# Expose port
EXPOSE 8000

# Set environment variables
ENV AWS_REGION=us-east-1
ENV UPLOAD_DIR=/app/uploads
ENV DB_PATH=/app/crm.db

# Run seed then start server
CMD ["sh", "-c", "python -m app.seed || true && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
