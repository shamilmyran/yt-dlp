from flask import Flask, request, jsonify, send_file
import yt_dlp
import os
import time
import uuid
from werkzeug.utils import secure_filename
import glob
import threading
import json
import subprocess
import re

app = Flask(__name__)

# Create directories
os.makedirs('/app/downloads', exist_ok=True)
os.makedirs('/app/status', exist_ok=True)
os.makedirs('/app/thumbnails', exist_ok=True)

# Auto-clean function (runs every hour)
def auto_clean_old_files():
    """Automatically clean files older than 1 hour"""
    while True:
        try:
            current_time = time.time()
            # Clean download files (1 hour old)
            for file_path in glob.glob('/app/downloads/*'):
                if os.path.isfile(file_path) and current_time - os.path.getctime(file_path) > 3600:
                    os.remove(file_path)
            
            # Clean status files (2 hours old)
            for status_file in glob.glob('/app/status/*.json'):
                if current_time - os.path.getctime(status_file) > 7200:
                    os.remove(status_file)
            
            # Clean thumbnails (3 hours old)
            for thumb_file in glob.glob('/app/thumbnails/*'):
                if current_time - os.path.getctime(thumb_file) > 10800:
                    os.remove(thumb_file)
            
            time.sleep(3600)  # Run every hour
        except:
            time.sleep(300)

# Start auto-clean thread
cleanup_thread = threading.Thread(target=auto_clean_old_files)
cleanup_thread.daemon = True
cleanup_thread.start()

# ULTRA FAST Options (15-30 seconds)
ultra_fast_opts = {
    'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio',
    'outtmpl': '/app/downloads/%(title)s.%(ext)s',
    'noplaylist': True,
    'socket_timeout': 15,
    'retries': 2,
    'fragment_retries': 2,
    'http_chunk_size': 10485760,
    'concurrent_fragment_downloads': 3,
    'ignoreerrors': True,
    'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15',
    'postprocessors': [],
    'noprogress': True,
    'quiet': True,
}

# HIGH QUALITY Options (MP3 conversion)
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
    'retries': 3,
    'ignoreerrors': True,
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
}

def extract_video_id(url):
    """Extract YouTube video ID from URL"""
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'youtu\.be\/([0-9A-Za-z_-]{11})',
        r'embed\/([0-9A-Za-z_-]{11})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match and len(match.group(1)) == 11:
            return match.group(1)
    return None

def download_thumbnail(video_id):
    """Download YouTube thumbnail"""
    try:
        # Try different thumbnail qualities
        for quality in ['maxresdefault', 'hqdefault', 'mqdefault', 'default']:
            thumbnail_url = f'https://img.youtube.com/vi/{video_id}/{quality}.jpg'
            try:
                response = subprocess.run([
                    'curl', '-s', '-f', '-L', '--max-time', '10',
                    thumbnail_url, '-o', f'/app/thumbnails/{video_id}.jpg'
                ], check=False)
                
                if response.returncode == 0 and os.path.exists(f'/app/thumbnails/{video_id}.jpg'):
                    return f'https://yt-dlp-munax.koyeb.app/thumbnail/{video_id}'
            except:
                continue
        return None
    except:
        return None

def download_task(url, job_id, options, format_type):
    status_file = f'/app/status/{job_id}.json'
    
    try:
        # Initial status
        status_data = {'status': 'processing', 'start_time': time.time()}
        with open(status_file, 'w') as f:
            json.dump(status_data, f)
        
        start_time = time.time()
        video_id = extract_video_id(url)
        
        # Try multiple download methods
        success = False
        for attempt in range(3):
            try:
                with yt_dlp.YoutubeDL(options) as ydl:
                    info = ydl.extract_info(url, download=True)
                    title = info.get('title', 'Audio') if info else 'Audio'
                    duration = info.get('duration', 0) if info else 0
                    success = True
                    break
            except:
                time.sleep(2)
                continue
        
        if not success:
            raise Exception("All download attempts failed")
        
        # Find downloaded file
        time.sleep(1)
        if format_type == 'fast':
            audio_files = [f for f in glob.glob('/app/downloads/*') if any(f.endswith(ext) for ext in ['.m4a', '.webm', '.opus'])]
        else:
            audio_files = glob.glob('/app/downloads/*.mp3')
        
        if not audio_files:
            raise Exception("Audio file not created")
        
        latest_file = max(audio_files, key=os.path.getctime)
        filename = os.path.basename(latest_file)
        safe_name = secure_filename(filename)
        
        # Get thumbnail
        thumbnail_url = download_thumbnail(video_id) if video_id else None
        
        status_data = {
            'status': 'completed',
            'title': title,
            'duration': duration,
            'download_time': round(time.time() - start_time, 2),
            'download_url': f"https://yt-dlp-munax.koyeb.app/download/{safe_name}",
            'thumbnail_url': thumbnail_url,
            'filename': filename,
            'video_id': video_id,
            'format': 'm4a/webm (fast)' if format_type == 'fast' else 'mp3 (quality)'
        }
        
    except Exception as e:
        status_data = {
            'status': 'failed', 
            'error': str(e),
            'failure_time': time.time()
        }
    
    with open(status_file, 'w') as f:
        json.dump(status_data, f)

@app.route('/download', methods=['GET'])
def download_audio():
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "URL parameter required (?url=)"}), 400
    
    if 'youtube.com/' not in url and 'youtu.be/' not in url:
        return jsonify({"error": "Only YouTube URLs supported"}), 400
    
    format_type = request.args.get('format', 'fast')
    options = mp3_opts if format_type == 'mp3' else ultra_fast_opts
    
    job_id = str(uuid.uuid4())
    
    thread = threading.Thread(target=download_task, args=(url, job_id, options, format_type))
    thread.daemon = True
    thread.start()
    
    estimated_time = "15-30 seconds" if format_type == 'fast' else "30-60 seconds"
    
    return jsonify({
        "status": "processing",
        "job_id": job_id,
        "check_status": f"https://yt-dlp-munax.koyeb.app/status/{job_id}",
        "estimated_time": estimated_time,
        "format": "m4a/webm (ultra fast)" if format_type == 'fast' else "mp3 (high quality)"
    })

@app.route('/status/<job_id>')
def check_status(job_id):
    status_file = f'/app/status/{job_id}.json'
    if not os.path.exists(status_file):
        return jsonify({"error": "Job not found"}), 404
    
    try:
        with open(status_file, 'r') as f:
            status_data = json.load(f)
        
        if status_data.get('status') == 'processing':
            elapsed = time.time() - status_data.get('start_time', time.time())
            status_data['elapsed_seconds'] = round(elapsed, 2)
        
        return jsonify(status_data)
    except:
        return jsonify({"error": "Error reading status"}), 500

@app.route('/download/<filename>')
def download_file(filename):
    try:
        safe_name = secure_filename(filename)
        file_path = f"/app/downloads/{safe_name}"
        
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        
        # Search for similar files
        all_files = glob.glob('/app/downloads/*')
        for actual_file in all_files:
            if secure_filename(os.path.basename(actual_file)) == safe_name:
                return send_file(actual_file, as_attachment=True)
        
        return jsonify({"error": "File not found"}), 404
    except Exception as e:
        return jsonify({"error": f"Download error: {str(e)}"}), 500

@app.route('/thumbnail/<video_id>')
def get_thumbnail(video_id):
    try:
        thumb_path = f'/app/thumbnails/{video_id}.jpg'
        if os.path.exists(thumb_path):
            return send_file(thumb_path, mimetype='image/jpeg')
        return jsonify({"error": "Thumbnail not found"}), 404
    except:
        return jsonify({"error": "Thumbnail error"}), 500

@app.route('/cleanup', methods=['POST'])
def manual_cleanup():
    """Manual cleanup endpoint"""
    try:
        deleted_files = 0
        for file_path in glob.glob('/app/downloads/*'):
            try:
                os.remove(file_path)
                deleted_files += 1
            except:
                pass
        
        return jsonify({
            "message": "Manual cleanup completed",
            "deleted_files": deleted_files,
            "auto_cleanup": "Running every hour automatically"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": time.time(),
        "auto_cleanup": "active",
        "files_count": len(glob.glob('/app/downloads/*')),
        "service": "yt-dlp-ultimate-api"
    })

@app.route('/')
def home():
    return jsonify({
        "message": "🎵 YouTube Audio Downloader API",
        "version": "3.0 - ULTIMATE",
        "status": "active",
        "features": [
            "⚡ Ultra-fast downloads (15-30s)",
            "🎵 High quality MP3 (30-60s)",
            "🖼️ Thumbnail support",
            "🧹 Auto-cleanup every hour",
            "🔧 Multiple fallback methods",
            "📱 WhatsApp bot ready"
        ],
        "endpoints": {
            "fast_download": "/download?url=URL&format=fast",
            "quality_download": "/download?url=URL&format=mp3",
            "check_status": "/status/JOB_ID",
            "download_file": "/download/FILENAME",
            "get_thumbnail": "/thumbnail/VIDEO_ID",
            "manual_cleanup": "/cleanup (POST)",
            "health_check": "/health"
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 ULTIMATE YouTube Audio API started on port {port}")
    app.run(host='0.0.0.0', port=port)
