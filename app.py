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

# ULTIMATE OPTIONS THAT WORK WITH COOKIES
ydl_opts = {
    'format': 'bestaudio/best',
    'outtmpl': '/app/downloads/%(title)s.%(ext)s',
    'noplaylist': True,
    'socket_timeout': 30,
    'retries': 10,
    'fragment_retries': 10,
    'ignoreerrors': True,
    'cookiefile': 'cookies.txt',  # USING YOUR COOKIES
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    # ANTI-BLOCK SETTINGS
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'web'],
            'skip': ['dash', 'hls']
        }
    },
    'throttled_rate': '1M',
    'sleep_interval': 2,
    'noprogress': True,
}

def download_task(url, job_id):
    """Simple download task that JUST WORKS"""
    status_file = f'/app/status/{job_id}.json'
    
    try:
        # Update status
        status_data = {'status': 'processing', 'start_time': time.time()}
        with open(status_file, 'w') as f:
            json.dump(status_data, f)
        
        start_time = time.time()
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Download the audio
            info_dict = ydl.extract_info(url, download=True)
            title = info_dict.get('title', 'Audio')
            
            # Find the downloaded file
            time.sleep(2)
            mp3_files = glob.glob('/app/downloads/*.mp3')
            if not mp3_files:
                raise Exception("MP3 file not created")
            
            latest_file = max(mp3_files, key=os.path.getctime)
            filename = os.path.basename(latest_file)
            safe_name = secure_filename(filename)
            
            status_data = {
                'status': 'completed',
                'title': title,
                'download_time': round(time.time() - start_time, 2),
                'download_url': f"https://yt-dlp-munax.koyeb.app/download/{safe_name}",
                'filename': filename
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
    """SIMPLE download endpoint"""
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "?url= missing"}), 400
    
    job_id = str(uuid.uuid4())
    
    thread = threading.Thread(target=download_task, args=(url, job_id))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "status": "started",
        "job_id": job_id,
        "check_status": f"https://yt-dlp-munax.koyeb.app/status/{job_id}"
    })

@app.route('/status/<job_id>')
def check_status(job_id):
    """Check status"""
    status_file = f'/app/status/{job_id}.json'
    if os.path.exists(status_file):
        with open(status_file, 'r') as f:
            return jsonify(json.load(f))
    return jsonify({"error": "Job not found"}), 404

@app.route('/download/<filename>')
def download_file(filename):
    """Download file"""
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
    return jsonify({"message": "Use /download?url=YOUTUBE_URL"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
