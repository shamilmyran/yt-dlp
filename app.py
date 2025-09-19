from flask import Flask, request, jsonify, send_file
import yt_dlp
import os
import time
import uuid
from werkzeug.utils import secure_filename
import glob
import threading
import json
import re
import shutil
from functools import wraps
from collections import defaultdict

app = Flask(__name__)

# Create directories if they don't exist
os.makedirs('/app/downloads', exist_ok=True)
os.makedirs('/app/status', exist_ok=True)

# Rate limiting
request_counts = defaultdict(int)
last_reset = time.time()

def rate_limit(max_requests=10, window=300):
    """Rate limiting decorator"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            global last_reset
            client_ip = request.remote_addr
            
            if time.time() - last_reset > window:
                request_counts.clear()
                last_reset = time.time()
            
            if request_counts[client_ip] >= max_requests:
                return jsonify({"error": "Rate limit exceeded. Try again later."}), 429
            
            request_counts[client_ip] += 1
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def is_valid_youtube_url(url):
    """Validate YouTube URL"""
    youtube_regex = re.compile(
        r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/'
        r'(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    )
    return youtube_regex.match(url) is not None

def extract_video_id(url):
    """Extract video ID from URL properly"""
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'youtu\.be\/([0-9A-Za-z_-]{11})',
        r'embed\/([0-9A-Za-z_-]{11})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            video_id = match.group(1)
            # Validate video ID length
            if len(video_id) == 11:
                return video_id
    return None

def cleanup_old_files():
    """Cleanup files older than 1 hour"""
    try:
        deleted_count = 0
        for file_path in glob.glob('/app/downloads/*'):
            if os.path.isfile(file_path) and time.time() - os.path.getctime(file_path) > 3600:
                os.remove(file_path)
                deleted_count += 1
        return deleted_count
    except:
        return 0

# FAST CONFIG - Optimized for speed
fast_opts = {
    'format': 'bestaudio[ext=m4a]/bestaudio/best',
    'outtmpl': '/app/downloads/%(title)s.%(ext)s',
    'noplaylist': True,
    'socket_timeout': 15,
    'retries': 2,
    'fragment_retries': 2,
    'ignoreerrors': True,
    'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15',
    'postprocessors': [],
    'noprogress': True,
}

# MP3 CONFIG - For MP3 conversion
mp3_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'outtmpl': '/app/downloads/%(title)s.%(ext)s',
    'noplaylist': True,
    'socket_timeout': 25,
    'retries': 2,
    'ignoreerrors': True,
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
}

def download_task(url, job_id, options, conversion_type="fast"):
    """Universal download task with proper caching handling"""
    status_file = f'/app/status/{job_id}.json'
    
    try:
        # Extract video ID properly
        video_id = extract_video_id(url)
        if not video_id:
            raise Exception("Invalid YouTube URL - Could not extract video ID")
        
        # Cleanup old files before starting new download
        cleanup_old_files()
        
        # Update status to processing
        status_data = {
            'status': 'processing',
            'url': url,
            'video_id': video_id,
            'start_time': time.time(),
            'message': 'Downloading audio...',
            'type': conversion_type
        }
        with open(status_file, 'w') as f:
            json.dump(status_data, f)
        
        start_time = time.time()
        
        with yt_dlp.YoutubeDL(options) as ydl:
            # Get info first
            info = ydl.extract_info(url, download=False)
            if not info:
                raise Exception("Could not get video information from YouTube")
            
            title = info.get('title', 'Unknown Title')
            duration = info.get('duration', 0)
            
            # Generate unique filename based on video ID to prevent caching issues
            unique_id = str(uuid.uuid4())[:8]
            options['outtmpl'] = f'/app/downloads/%(title)s_{unique_id}.%(ext)s'
            
            # Download
            ydl.download([url])
            
            download_time = time.time() - start_time
            
            # Find downloaded file with the unique pattern
            time.sleep(1)
            all_files = glob.glob('/app/downloads/*')
            
            if not all_files:
                raise Exception("No audio file was created after download")
            
            # Get the newest file (should be our download)
            latest_file = max(all_files, key=os.path.getctime)
            base_name = os.path.basename(latest_file)
            safe_name = secure_filename(base_name)
            
            # Update status to completed
            status_data = {
                'status': 'completed',
                'url': url,
                'video_id': video_id,
                'download_time': round(download_time, 2),
                'download_url': f"https://yt-dlp-munax.koyeb.app/download-file/{safe_name}",
                'filename': base_name,
                'safe_filename': safe_name,
                'title': title,
                'duration': duration,
                'completion_time': time.time(),
                'format': 'MP3' if conversion_type == 'mp3' else 'Audio',
                'type': conversion_type,
                'file_size': os.path.getsize(latest_file) if os.path.exists(latest_file) else 0
            }
            
    except Exception as e:
        # Update status to failed
        status_data = {
            'status': 'failed',
            'url': url,
            'error': str(e),
            'failure_time': time.time(),
            'type': conversion_type
        }
    
    # Save status
    with open(status_file, 'w') as f:
        json.dump(status_data, f)

@app.route('/audio', methods=['GET'])
@rate_limit(max_requests=8, window=300)
def audio_download():
    """Main audio download endpoint"""
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "No URL provided. Use ?url=YOUTUBE_URL"}), 400
    
    # Cleanup old files before starting new download
    cleanup_old_files()
    
    if not is_valid_youtube_url(url):
        return jsonify({"error": "Invalid YouTube URL"}), 400
    
    # Get download type from parameter or default to fast
    download_type = request.args.get('type', 'fast')
    options = mp3_opts if download_type == 'mp3' else fast_opts
    
    job_id = str(uuid.uuid4())
    
    thread = threading.Thread(target=download_task, args=(url, job_id, options, download_type))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "status": "processing", 
        "message": "Audio download started",
        "job_id": job_id,
        "check_status": f"https://yt-dlp-munax.koyeb.app/status/{job_id}",
        "estimated_time": "10-25 seconds",
        "type": download_type
    })

@app.route('/status/<job_id>')
def check_status(job_id):
    """Check download status"""
    status_file = f'/app/status/{job_id}.json'
    
    if not os.path.exists(status_file):
        return jsonify({"error": "Job not found"}), 404
    
    try:
        with open(status_file, 'r') as f:
            status_data = json.load(f)
            
        # Add current time info for processing jobs
        if status_data['status'] == 'processing':
            elapsed = time.time() - status_data['start_time']
            status_data['elapsed_seconds'] = round(elapsed, 2)
            
        return jsonify(status_data)
    except:
        return jsonify({"error": "Error reading status"}), 500

@app.route('/download-file/<filename>')
def download_file(filename):
    """Download audio file"""
    try:
        safe_filename = secure_filename(filename)
        
        # Search for the file
        all_files = glob.glob('/app/downloads/*')
        for actual_file in all_files:
            actual_filename = os.path.basename(actual_file)
            if secure_filename(actual_filename) == safe_filename:
                return send_file(actual_file, as_attachment=True, download_name=safe_filename)
        
        return jsonify({"error": "File not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/cleanup', methods=['POST'])
def cleanup_files():
    """Clean ALL files and statuses"""
    try:
        deleted_files = 0
        deleted_status = 0
        
        # Clean ALL files in downloads
        for file_path in glob.glob('/app/downloads/*'):
            try:
                os.remove(file_path)
                deleted_files += 1
            except:
                pass
        
        # Clean ALL status files
        for status_path in glob.glob('/app/status/*.json'):
            try:
                os.remove(status_path)
                deleted_status += 1
            except:
                pass
        
        return jsonify({
            "message": "Complete cleanup completed",
            "deleted_files": deleted_files,
            "deleted_status_files": deleted_status,
            "remaining_files": len(glob.glob('/app/downloads/*'))
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": time.time(),
        "service": "yt-dlp-audio-api",
        "downloads_folder": os.path.exists('/app/downloads'),
        "files_count": len(glob.glob('/app/downloads/*'))
    })

@app.route('/')
def home():
    """API documentation"""
    return jsonify({
        "message": "YouTube Audio Downloader API",
        "version": "2.1",
        "status": "active",
        "endpoints": {
            "audio_download": "/audio?url=YOUTUBE_URL&type=fast",
            "check_status": "/status/JOB_ID",
            "download_file": "/download-file/FILENAME",
            "cleanup": "/cleanup (POST)",
            "health": "/health"
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # Cleanup on startup
    cleanup_old_files()
    app.run(host='0.0.0.0', port=port, debug=False)
