FROM python:3.11-slim

# Install system deps
RUN apt-get update && \
    apt-get install -y ffmpeg curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python packages
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy app
COPY . .

# Create download directory
RUN mkdir -p /app/downloads

# NO GUNICORN - SIMPLE FLASK
CMD python app.py
