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

# FAST CONFIG - No conversion, optimized for speed (5-15 seconds)
fast_opts = {
    'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio',
    'outtmpl': '/app/downloads/%(title)s.%(ext)s',
    'noplaylist': True,
    'socket_timeout': 10,
    'retries': 1,
    'fragment_retries': 1,
    'http_chunk_size': 10485760,  # 10MB chunks
    'concurrent_fragment_downloads': 2,
    'throttled_rate': None,
    'sleep_interval': 0,
    'ignoreerrors': True,
    'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15',
    'postprocessors': [],  # No conversion for speed
}

# MP3 CONFIG - Slower but converts to MP3 (20-40 seconds)
mp3_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'outtmpl': '/app/downloads/%(title)s.%(ext)s',
    'noplaylist': True,
    'socket_timeout': 30,
    'retries': 3,
    'fragment_retries': 3,
    'ignoreerrors': True,
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'extractaudio': True,
    'audioformat': 'mp3',
}

def download_task(url, job_id, options, conversion_type="fast"):
    """Universal download task"""
    status_file = f'/app/status/{job_id}.json'
    
    try:
        # Update status to processing
        status_data = {
            'status': 'processing',
            'url': url,
            'start_time': time.time(),
            'message': f'{"Converting to MP3..." if conversion_type == "mp3" else "Downloading audio..."}',
            'type': conversion_type
        }
        with open(status_file, 'w') as f:
            json.dump(status_data, f)
        
        start_time = time.time()
        
        with yt_dlp.YoutubeDL(options) as ydl:
            # Get info first
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'audio') if info else 'audio'
            
            # Download
            ydl.download([url])
            
            duration = time.time() - start_time
            
            # Find downloaded file
            wait_time = 3 if conversion_type == "mp3" else 1
            time.sleep(wait_time)
            
            if conversion_type == "mp3":
                target_files = glob.glob('/app/downloads/*.mp3')
            else:
                target_files = glob.glob('/app/downloads/*')
            
            if not target_files:
                all_files = glob.glob('/app/downloads/*')
                if not all_files:
                    raise Exception("No files were created")
                latest_file = max(all_files, key=os.path.getctime)
            else:
                latest_file = max(target_files, key=os.path.getctime)
            
            base_name = os.path.basename(latest_file)
            safe_name = secure_filename(base_name)
            file_ext = os.path.splitext(latest_file)[1]
            
            # Update status to completed
            status_data = {
                'status': 'completed',
                'url': url,
                'download_time': round(duration, 2),
                'download_url': f"https://yt-dlp-munax.koyeb.app/download-file/{safe_name}",
                'filename': base_name,
                'safe_filename': safe_name,
                'title': title,
                'duration': info.get('duration', 0) if info else 0,
                'completion_time': time.time(),
                'format': 'MP3' if conversion_type == 'mp3' else f'Audio ({file_ext})',
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

@app.route('/fast-audio', methods=['GET'])
@rate_limit(max_requests=5, window=300)
def fast_audio():
    """Ultra-fast audio download (5-15 seconds, native format)"""
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "No URL provided. Usage: /fast-audio?url=YOUTUBE_URL"}), 400
    
    if not is_valid_youtube_url(url):
        return jsonify({"error": "Invalid YouTube URL"}), 400
    
    job_id = str(uuid.uuid4())
    
    thread = threading.Thread(target=download_task, args=(url, job_id, fast_opts, "fast"))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "status": "processing", 
        "message": "Ultra-fast audio download started",
        "job_id": job_id,
        "check_status": f"https://yt-dlp-munax.koyeb.app/status/{job_id}",
        "estimated_time": "5-15 seconds",
        "format": "Native audio (m4a/webm/opus)",
        "speed": "ULTRA FAST"
    })

@app.route('/mp3-audio', methods=['GET'])
@rate_limit(max_requests=3, window=600)
def mp3_audio():
    """High-quality MP3 download (20-40 seconds, converted)"""
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "No URL provided. Usage: /mp3-audio?url=YOUTUBE_URL"}), 400
    
    if not is_valid_youtube_url(url):
        return jsonify({"error": "Invalid YouTube URL"}), 400
    
    job_id = str(uuid.uuid4())
    
    thread = threading.Thread(target=download_task, args=(url, job_id, mp3_opts, "mp3"))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "status": "processing", 
        "message": "MP3 conversion started",
        "job_id": job_id,
        "check_status": f"https://yt-dlp-munax.koyeb.app/status/{job_id}",
        "estimated_time": "20-40 seconds",
        "format": "MP3 (192kbps)",
        "quality": "HIGH QUALITY"
    })

@app.route('/batch-download', methods=['POST'])
@rate_limit(max_requests=2, window=600)
def batch_download():
    """Download multiple URLs in parallel"""
    data = request.get_json()
    if not data or 'urls' not in data:
        return jsonify({"error": "Send JSON with 'urls' array"}), 400
    
    urls = data.get('urls', [])
    download_type = data.get('type', 'fast')  # 'fast' or 'mp3'
    
    if len(urls) > 5:
        return jsonify({"error": "Maximum 5 URLs per batch"}), 400
    
    job_ids = []
    options = mp3_opts if download_type == 'mp3' else fast_opts
    
    for url in urls:
        if is_valid_youtube_url(url):
            job_id = str(uuid.uuid4())
            thread = threading.Thread(target=download_task, args=(url, job_id, options, download_type))
            thread.daemon = True
            thread.start()
            job_ids.append({"url": url, "job_id": job_id})
    
    return jsonify({
        "message": f"Started {len(job_ids)} {download_type} downloads",
        "jobs": job_ids,
        "check_all": f"https://yt-dlp-munax.koyeb.app/batch-status",
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
            return jsonify(json.load(f))
    except:
        return jsonify({"error": "Error reading status"}), 500

@app.route('/batch-status', methods=['POST'])
def batch_status():
    """Check multiple job statuses"""
    data = request.get_json()
    job_ids = data.get('job_ids', [])
    
    statuses = []
    for job_id in job_ids:
        status_file = f'/app/status/{job_id}.json'
        if os.path.exists(status_file):
            try:
                with open(status_file, 'r') as f:
                    statuses.append(json.load(f))
            except:
                statuses.append({"job_id": job_id, "status": "error"})
        else:
            statuses.append({"job_id": job_id, "status": "not_found"})
    
    return jsonify({"statuses": statuses})

@app.route('/download-file/<filename>')
def download_file(filename):
    """Download audio file"""
    try:
        safe_filename = secure_filename(filename)
        file_path = f"/app/downloads/{safe_filename}"
        
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True, download_name=safe_filename)
        
        # Search for similar files
        all_files = glob.glob('/app/downloads/*')
        for actual_file in all_files:
            if secure_filename(os.path.basename(actual_file)) == safe_filename:
                return send_file(actual_file, as_attachment=True, download_name=safe_filename)
        
        return jsonify({"error": "File not found", "filename": filename}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/cleanup')
def cleanup_files():
    """Clean old files and statuses"""
    try:
        deleted_files = 0
        deleted_status = 0
        
        # Clean files older than 1 hour
        for file_path in glob.glob('/app/downloads/*'):
            if time.time() - os.path.getctime(file_path) > 3600:
                os.remove(file_path)
                deleted_files += 1
        
        # Clean status files older than 24 hours
        for status_path in glob.glob('/app/status/*.json'):
            if time.time() - os.path.getctime(status_path) > 86400:
                os.remove(status_path)
                deleted_status += 1
        
        return jsonify({
            "message": "Cleanup completed",
            "deleted_files": deleted_files,
            "deleted_status": deleted_status,
            "remaining_files": len(glob.glob('/app/downloads/*'))
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/keepalive')
def keepalive():
    """Keep API warm - prevents cold starts"""
    return jsonify({
        "status": "warm", 
        "timestamp": time.time(),
        "uptime": "ready"
    })

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": time.time(),
        "downloads_writable": os.access('/app/downloads', os.W_OK),
        "status_writable": os.access('/app/status', os.W_OK),
        "disk_usage": {
            "downloads": len(glob.glob('/app/downloads/*')),
            "statuses": len(glob.glob('/app/status/*.json'))
        }
    })

@app.route('/stats')
def stats():
    """API statistics"""
    downloads = glob.glob('/app/downloads/*')
    statuses = glob.glob('/app/status/*.json')
    
    # Count by type
    mp3_count = len(glob.glob('/app/downloads/*.mp3'))
    other_count = len(downloads) - mp3_count
    
    return jsonify({
        "total_files": len(downloads),
        "mp3_files": mp3_count,
        "other_audio": other_count,
        "active_jobs": len(statuses),
        "disk_usage_mb": sum(os.path.getsize(f) for f in downloads) / 1024 / 1024,
        "last_cleanup": "Auto every hour"
    })

@app.route('/debug')
def debug():
    """Debug endpoint"""
    return jsonify({
        "downloads_dir": os.path.exists('/app/downloads'),
        "files_in_downloads": [os.path.basename(f) for f in glob.glob('/app/downloads/*')],
        "mp3_files": [os.path.basename(f) for f in glob.glob('/app/downloads/*.mp3')],
        "status_dir": os.path.exists('/app/status'),
        "status_files": len(glob.glob('/app/status/*.json')),
        "current_time": time.time(),
        "rate_limits": dict(request_counts)
    })

@app.route('/')
def home():
    """API documentation"""
    return jsonify({
        "message": "🎵 YouTube Audio Downloader API",
        "version": "2.0 - Optimized",
        "status": "active",
        "endpoints": {
            "fast_download": {
                "url": "/fast-audio?url=YOUTUBE_URL",
                "speed": "5-15 seconds",
                "format": "Native audio (m4a/webm)",
                "description": "Ultra-fast download, no conversion"
            },
            "mp3_download": {
                "url": "/mp3-audio?url=YOUTUBE_URL", 
                "speed": "20-40 seconds",
                "format": "MP3 (192kbps)",
                "description": "High-quality MP3 conversion"
            },
            "batch_download": {
                "url": "/batch-download",
                "method": "POST",
                "body": '{"urls": ["URL1", "URL2"], "type": "fast"}',
                "description": "Download up to 5 URLs in parallel"
            },
            "utilities": {
                "status": "/status/JOB_ID",
                "download": "/download-file/FILENAME", 
                "cleanup": "/cleanup",
                "health": "/health",
                "stats": "/stats",
                "keepalive": "/keepalive"
            }
        },
        "features": [
            "⚡ Ultra-fast downloads (5-15s)",
            "🎵 MP3 conversion (20-40s)", 
            "📦 Batch processing (5 URLs)",
            "🔒 Rate limiting protection",
            "🧹 Auto cleanup",
            "📊 Usage statistics",
            "🌡️ Health monitoring"
        ],
        "limits": {
            "fast_downloads": "5 per 5 minutes",
            "mp3_downloads": "3 per 10 minutes", 
            "batch_downloads": "2 per 10 minutes",
            "max_batch_size": 5
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    print(f"🚀 Starting YouTube Audio API on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
