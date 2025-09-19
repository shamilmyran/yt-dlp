FROM python:3.11-slim

# Install FFmpeg and dependencies properly
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create downloads directory with proper permissions
RUN mkdir -p /app/downloads && \
    chmod 777 /app/downloads

EXPOSE 5000

CMD gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 app:app
