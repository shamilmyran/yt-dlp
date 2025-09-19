from flask import Flask, request, jsonify
import yt_dlp
import os
import time

app = Flask(__name__)

# Enhanced configuration with cookies and anti-bot measures
ydl_opts_fast = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'outtmpl': '/tmp/%(title)s.%(ext)s',
    'noplaylist': True,
    'socket_timeout': 30,
    'retries': 10,
    'fragment_retries': 10,
    'extract_flat': False,
    'ignoreerrors': True,
    
    # Cookie authentication to avoid bot detection
    'cookiefile': 'cookies.txt',
    
    # Advanced options to avoid blocking
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'referer': 'https://www.youtube.com/',
    'throttled_rate': '1M',
    'sleep_interval': 2,
    'max_sleep_interval': 5,
    'extractor_args': {
        'youtube': {
            'player_client': ['web', 'android'],
            'skip': ['dash', 'hls']
        }
    },
    'compat_opts': ['no-youtube-unavailable-videos', 'no-playlist-metafiles'],
}

# Additional configuration for video downloads
ydl_opts_video = {
    'format': 'best[height<=720]',
    'outtmpl': '/tmp/%(title)s.%(ext)s',
    'noplaylist': True,
    'socket_timeout': 30,
    'retries': 10,
    'fragment_retries': 10,
    'ignoreerrors': True,
    'cookiefile': 'cookies.txt',
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'throttled_rate': '2M',
    'sleep_interval': 3,
}

@app.route('/')
def home():
    return jsonify({
        "message": "YT-DLP API is running successfully!",
        "status": "active",
        "endpoints": {
            "audio": "/fast-audio?url=YOUTUBE_URL",
            "video": "/download-video?url=YOUTUBE_URL",
            "info": "/video-info?url=YOUTUBE_URL"
        }
    })

@app.route('/fast-audio', methods=['GET'])
def fast_audio():
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "No URL provided. Use ?url=YOUTUBE_URL"}), 400
    
    try:
        start_time = time.time()
        
        with yt_dlp.YoutubeDL(ydl_opts_fast) as ydl:
            info = ydl.extract_info(url, download=True)
            
            duration = time.time() - start_time
            
            return jsonify({
                "status": "success", 
                "title": info.get('title', 'Unknown Title'),
                "duration": info.get('duration', 0),
                "download_time": round(duration, 2),
                "message": "Audio downloaded successfully as MP3"
            })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/download-video', methods=['GET'])
def download_video():
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "No URL provided. Use ?url=YOUTUBE_URL"}), 400
    
    try:
        start_time = time.time()
        
        with yt_dlp.YoutubeDL(ydl_opts_video) as ydl:
            info = ydl.extract_info(url, download=True)
            
            duration = time.time() - start_time
            
            return jsonify({
                "status": "success", 
                "title": info.get('title', 'Unknown Title'),
                "duration": info.get('duration', 0),
                "format": info.get('format', 'Unknown Format'),
                "download_time": round(duration, 2),
                "message": "Video downloaded successfully"
            })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/video-info', methods=['GET'])
def video_info():
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "No URL provided. Use ?url=YOUTUBE_URL"}), 400
    
    try:
        # Options for info extraction only (no download)
        info_opts = {
            'quiet': True,
            'no_warnings': False,
            'cookiefile': 'cookies.txt',
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            return jsonify({
                "status": "success", 
                "title": info.get('title'),
                "duration": info.get('duration'),
                "uploader": info.get('uploader'),
                "view_count": info.get('view_count'),
                "formats": [{
                    "format_id": f.get('format_id'),
                    "ext": f.get('ext'),
                    "resolution": f.get('resolution'),
                    "filesize": f.get('filesize')
                } for f in info.get('formats', [])[:5]]  # First 5 formats only
            })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": time.time(),
        "service": "yt-dlp-api"
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
