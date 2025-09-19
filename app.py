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

os.makedirs('/app/downloads', exist_ok=True)
os.makedirs('/app/status', exist_ok=True)

# ⚡ ULTRA FAST OPTIONS (15-30 seconds)
ultra_fast_opts = {
    'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio',
    'outtmpl': '/app/downloads/%(title)s.%(ext)s',
    'noplaylist': True,
    'socket_timeout': 10,
    'retries': 1,
    'fragment_retries': 1,
    'http_chunk_size': 15728640,  # 15MB chunks
    'concurrent_fragment_downloads': 4,  # Parallel downloads
    'throttled_rate': None,  # No speed limit
    'sleep_interval': 0,     # No delay
    'ignoreerrors': True,
    'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15',
    'postprocessors': [],    # NO CONVERSION = MAX SPEED
    'noprogress': True,
    'quiet': True,
}

# 🎵 MP3 Options (30-60 seconds - better quality)
mp3_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'outtmpl': '/app/downloads/%(title)s.%(ext)s',
    'noplaylist': True,
    'socket_timeout': 20,
    'retries': 2,
    'ignoreerrors': True,
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
}

def download_task(url, job_id, options, format_type):
    status_file = f'/app/status/{job_id}.json'
    
    try:
        status_data = {'status': 'processing', 'start_time': time.time()}
        with open(status_file, 'w') as f:
            json.dump(status_data, f)
        
        start_time = time.time()
        
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'Audio')
            duration = info.get('duration', 0)
            
            # Find downloaded file
            time.sleep(1)
            if format_type == 'fast':
                audio_files = glob.glob('/app/downloads/*.*')
                audio_files = [f for f in audio_files if f.endswith(('.m4a', '.webm', '.opus'))]
            else:
                audio_files = glob.glob('/app/downloads/*.mp3')
            
            if not audio_files:
                raise Exception("Audio file not created")
            
            latest_file = max(audio_files, key=os.path.getctime)
            filename = os.path.basename(latest_file)
            safe_name = secure_filename(filename)
            
            status_data = {
                'status': 'completed',
                'title': title,
                'duration': duration,
                'download_time': round(time.time() - start_time, 2),
                'download_url': f"https://yt-dlp-munax.koyeb.app/download/{safe_name}",
                'filename': filename,
                'format': 'm4a/webm (fast)' if format_type == 'fast' else 'mp3 (quality)'
            }
            
    except Exception as e:
        status_data = {'status': 'failed', 'error': str(e)}
    
    with open(status_file, 'w') as f:
        json.dump(status_data, f)

@app.route('/download', methods=['GET'])
def download_audio():
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "?url= missing"}), 400
    
    # Choose format: fast (m4a) or mp3 (quality)
    format_type = request.args.get('format', 'fast')
    options = mp3_opts if format_type == 'mp3' else ultra_fast_opts
    
    job_id = str(uuid.uuid4())
    
    thread = threading.Thread(target=download_task, args=(url, job_id, options, format_type))
    thread.daemon = True
    thread.start()
    
    estimated_time = "15-30 seconds" if format_type == 'fast' else "30-60 seconds"
    
    return jsonify({
        "status": "started",
        "job_id": job_id,
        "check_status": f"https://yt-dlp-munax.koyeb.app/status/{job_id}",
        "estimated_time": estimated_time,
        "format": "m4a/webm (ultra fast)" if format_type == 'fast' else "mp3 (high quality)"
    })

@app.route('/status/<job_id>')
def check_status(job_id):
    status_file = f'/app/status/{job_id}.json'
    if os.path.exists(status_file):
        with open(status_file, 'r') as f:
            return jsonify(json.load(f))
    return jsonify({"error": "Job not found"}), 404

@app.route('/download/<filename>')
def download_file(filename):
    try:
        safe_name = secure_filename(filename)
        file_path = f"/app/downloads/{safe_name}"
        
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        return jsonify({"error": "File not found"}), 404
    except:
        return jsonify({"error": "Download error"}), 500

@app.route('/')
def home():
    return jsonify({
        "message": "YouTube Audio Downloader",
        "endpoints": {
            "fast_download": "/download?url=URL&format=fast",
            "quality_download": "/download?url=URL&format=mp3",
            "check_status": "/status/JOB_ID"
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
