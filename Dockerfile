FROM python:3.11-slim

# Install system dependencies + latest tools
RUN apt-get update && \
    apt-get install -y \
    ffmpeg \
    curl \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install LATEST yt-dlp with impersonation support
RUN curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp && \
    chmod a+rx /usr/local/bin/yt-dlp

# Alternative: Install via pip for latest features
# RUN pip install --no-cache-dir "yt-dlp[default]" && \
#     yt-dlp --update

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create directories
RUN mkdir -p /app/downloads /app/metadata

EXPOSE 8000

# Verify installations and check impersonation support
RUN yt-dlp --version && \
    yt-dlp --help | grep -i impersonate && \
    ffmpeg -version | head -n 1

CMD ["python", "app.py"]
