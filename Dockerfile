FROM python:3.11-slim

# Install system dependencies + yt-dlp
RUN apt-get update && \
    apt-get install -y ffmpeg curl && \
    pip install yt-dlp==2023.11.16 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "app.py"]
