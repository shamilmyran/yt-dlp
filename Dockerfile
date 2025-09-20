FROM python:3.11-slim

# Install dependencies
RUN apt-get update && \
    apt-get install -y ffmpeg curl && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

WORKDIR /app

# Install Python packages
RUN pip install yt-dlp flask

COPY . .

# Create directories
RUN mkdir -p /app/downloads /app/status /app/thumbnails

EXPOSE 5000

CMD ["python", "app.py"]
