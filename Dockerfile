FROM python:3.11-slim

WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variables
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# Cloud Run will provide PORT automatically
# Firebase credentials should be set via environment variables in Cloud Run
EXPOSE 8080

# Run the ADK web server
# --host 0.0.0.0 is required for Cloud Run to accept external traffic
# --port ${PORT} uses the Cloud Run provided port (default 8080)
# --no-reload disables auto-reload (not supported in Cloud Run)
# --allow_origins * allows CORS from any origin (adjust as needed)
CMD adk web . --host 0.0.0.0 --port ${PORT} --no-reload --allow_origins "*"