from flask import Flask, request, jsonify, send_file
import yt_dlp
import os
import time
import uuid
from werkzeug.utils import secure_filename
import glob
import threading
import json

app = Flask(__name__)

# Create directories if they don't exist
os.makedirs('/app/downloads', exist_ok=True)
os.makedirs('/app/status', exist_ok=True)

ydl_opts_fast = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'outtmpl': '/app/downloads/%(title)s.%(ext)s',
    'noplaylist': True,
    'socket_timeout': 30,
    'retries': 5,
    'fragment_retries': 5,
    'ignoreerrors': True,
    'cookiefile': 'cookies.txt',
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'throttled_rate': '2M',
    'sleep_interval': 1,
    'noprogress': True,
}

def download_audio_task(url, job_id):
    """Background task to download audio"""
    status_file = f'/app/status/{job_id}.json'
    
    try:
        # Update status to processing
        status_data = {
            'status': 'processing',
            'url': url,
            'start_time': time.time(),
            'message': 'Download started'
        }
        with open(status_file, 'w') as f:
            json.dump(status_data, f)
        
        start_time = time.time()
        
        with yt_dlp.YoutubeDL(ydl_opts_fast) as ydl:
            # Extract info first to get title
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'audio') if info else 'audio'
            
            # Now download
            ydl.download([url])
            
            duration = time.time() - start_time
            
            # Find the downloaded file
            time.sleep(2)  # Give time for file conversion
            audio_files = glob.glob('/app/downloads/*.*')
            audio_files = [f for f in audio_files if f.endswith(('.mp3', '.webm', '.m4a', '.opus'))]
            
            if not audio_files:
                raise Exception("No audio file was created after download")
            
            latest_file = max(audio_files, key=os.path.getctime)
            base_name = os.path.basename(latest_file)
            safe_name = secure_filename(base_name)
            
            # Update status to completed
            status_data = {
                'status': 'completed',
                'url': url,
                'download_time': round(duration, 2),
                'download_url': f"https://yt-dlp-munax.koyeb.app/download-file/{safe_name}",
                'filename': base_name,
                'title': title,
                'duration': info.get('duration', 0) if info else 0,
                'completion_time': time.time()
            }
            
    except Exception as e:
        # Update status to failed
        status_data = {
            'status': 'failed',
            'url': url,
            'error': str(e),
            'failure_time': time.time()
        }
    
    # Save status (whether success or failure)
    with open(status_file, 'w') as f:
        json.dump(status_data, f)

@app.route('/fast-audio', methods=['GET'])
def fast_audio():
    """Instant response endpoint - starts download in background"""
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "No URL provided. Use ?url=YOUTUBE_URL"}), 400
    
    # Generate unique job ID
    job_id = str(uuid.uuid4())
    
    # Start download in background thread
    thread = threading.Thread(target=download_audio_task, args=(url, job_id))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "status": "processing", 
        "message": "Audio download started. Please check back in 15-30 seconds.",
        "job_id": job_id,
        "check_status": f"https://yt-dlp-munax.koyeb.app/status/{job_id}",
        "estimated_time": "15-30 seconds"
    })

@app.route('/status/<job_id>')
def check_status(job_id):
    """Check status of a download job"""
    status_file = f'/app/status/{job_id}.json'
    
    if not os.path.exists(status_file):
        return jsonify({"error": "Job not found"}), 404
    
    try:
        with open(status_file, 'r') as f:
            status_data = json.load(f)
        
        return jsonify(status_data)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/download-file/<filename>')
def download_file(filename):
    """Download the audio file"""
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

@app.route('/direct-audio', methods=['GET'])
def direct_audio():
    """Direct download (wait for completion) - for testing"""
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    
    try:
        start_time = time.time()
        
        with yt_dlp.YoutubeDL(ydl_opts_fast) as ydl:
            # Extract info first
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'Unknown Title') if info else 'Unknown Title'
            
            # Download
            ydl.download([url])
            
            duration = time.time() - start_time
            
            # Find the downloaded file
            time.sleep(2)
            audio_files = glob.glob('/app/downloads/*.*')
            audio_files = [f for f in audio_files if f.endswith(('.mp3', '.webm', '.m4a', '.opus'))]
            
            if not audio_files:
                return jsonify({"error": "No audio file created"}), 500
            
            latest_file = max(audio_files, key=os.path.getctime)
            base_name = os.path.basename(latest_file)
            safe_name = secure_filename(base_name)
            
            return jsonify({
                "status": "success", 
                "title": title,
                "duration": info.get('duration', 0) if info else 0,
                "download_time": round(duration, 2),
                "download_url": f"https://yt-dlp-munax.koyeb.app/download-file/{safe_name}",
                "filename": base_name,
                "message": "Audio downloaded successfully"
            })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/cleanup-files')
def cleanup_files():
    """Cleanup old files"""
    try:
        files = glob.glob('/app/downloads/*')
        deleted_count = 0
        for file_path in files:
            if os.path.isfile(file_path) and time.time() - os.path.getctime(file_path) > 3600:
                os.remove(file_path)
                deleted_count += 1
        
        # Cleanup status files older than 24 hours
        status_files = glob.glob('/app/status/*.json')
        status_deleted = 0
        for status_file in status_files:
            if time.time() - os.path.getctime(status_file) > 86400:
                os.remove(status_file)
                status_deleted += 1
        
        return jsonify({
            "message": "Cleanup completed", 
            "deleted_files": deleted_count,
            "deleted_status_files": status_deleted,
            "remaining_files": len(glob.glob('/app/downloads/*'))
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/')
def home():
    return jsonify({
        "message": "YT-DLP WhatsApp Audio Downloader API",
        "status": "active",
        "endpoints": {
            "instant_start": "/fast-audio?url=YOUTUBE_URL",
            "check_status": "/status/JOB_ID",
            "direct_download": "/direct-audio?url=YOUTUBE_URL",
            "file_download": "/download-file/FILENAME.mp3",
            "cleanup": "/cleanup-files"
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
