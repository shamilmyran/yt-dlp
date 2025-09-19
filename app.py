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

# SIMPLE CONFIG - No conversion, just download audio
ydl_opts = {
    'format': 'bestaudio/best',
    'outtmpl': '/app/downloads/%(title)s.%(ext)s',
    'noplaylist': True,
    'socket_timeout': 30,
    'retries': 3,
    'ignoreerrors': True,
    'cookiefile': 'cookies.txt',
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    # No complex postprocessing - just download
    'postprocessors': [],
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
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Get info first to check if video exists
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'audio') if info else 'audio'
            
            # Now download
            ydl.download([url])
            
            duration = time.time() - start_time
            
            # Find the downloaded file (wait a bit)
            time.sleep(2)
            all_files = glob.glob('/app/downloads/*')
            
            if not all_files:
                raise Exception("No files were created in downloads directory")
            
            # Get the newest file
            latest_file = max(all_files, key=os.path.getctime)
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
    
    # Save status
    with open(status_file, 'w') as f:
        json.dump(status_data, f)

@app.route('/fast-audio', methods=['GET'])
def fast_audio():
    """Start audio download"""
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    
    # Generate unique job ID
    job_id = str(uuid.uuid4())
    
    # Start download in background
    thread = threading.Thread(target=download_audio_task, args=(url, job_id))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "status": "processing", 
        "message": "Audio download started",
        "job_id": job_id,
        "check_status": f"https://yt-dlp-munax.koyeb.app/status/{job_id}",
        "estimated_time": "15-30 seconds"
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

@app.route('/download-file/<filename>')
def download_file(filename):
    """Download audio file"""
    try:
        safe_filename = secure_filename(filename)
        file_path = f"/app/downloads/{safe_filename}"
        
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        
        # Search for similar files
        all_files = glob.glob('/app/downloads/*')
        for actual_file in all_files:
            if secure_filename(os.path.basename(actual_file)) == safe_filename:
                return send_file(actual_file, as_attachment=True)
        
        return jsonify({"error": "File not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/debug')
def debug():
    """Debug endpoint to check system"""
    return jsonify({
        "downloads_dir_exists": os.path.exists('/app/downloads'),
        "files_in_downloads": glob.glob('/app/downloads/*'),
        "status_dir_exists": os.path.exists('/app/status'),
        "status_files": glob.glob('/app/status/*.json'),
        "current_time": time.time()
    })

@app.route('/')
def home():
    return jsonify({"message": "YT-DLP API is running", "status": "active"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
