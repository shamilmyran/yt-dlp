from flask import Flask, request, jsonify, send_file
import subprocess
import os
import uuid
import time
import threading
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Create directories
os.makedirs('/app/downloads', exist_ok=True)

# Global storage for jobs
jobs = {}

def simple_download(url, job_id):
    """Dead simple yt-dlp download - NO FANCY SHIT"""
    try:
        jobs[job_id] = {'status': 'processing', 'start_time': time.time()}
        
        file_id = str(uuid.uuid4())[:8]
        output_file = f"/app/downloads/audio_{file_id}.mp3"
        
        # SIMPLE COMMAND - NO COMPLEX OPTIONS
        cmd = [
            'yt-dlp', 
            '-x', 
            '--audio-format', 'mp3',
            '--no-warnings',
            '--quiet',
            '-o', output_file,
            url
        ]
        
        # Run it
        result = subprocess.run(cmd, timeout=180, capture_output=True)
        
        if result.returncode == 0 and os.path.exists(output_file):
            filename = os.path.basename(output_file)
            jobs[job_id] = {
                'status': 'completed',
                'filename': filename,
                'download_url': f'https://yt-dlp-munax.koyeb.app/file/{filename}'
            }
        else:
            jobs[job_id] = {'status': 'failed', 'error': 'Download failed'}
            
    except Exception as e:
        jobs[job_id] = {'status': 'failed', 'error': str(e)}

@app.route('/download')
def download():
    """Simple download endpoint"""
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    job_id = str(uuid.uuid4())
    
    # Start background download
    thread = threading.Thread(target=simple_download, args=(url, job_id))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'job_id': job_id,
        'status': 'processing',
        'check_url': f'https://yt-dlp-munax.koyeb.app/status/{job_id}'
    })

@app.route('/status/<job_id>')
def status(job_id):
    """Check job status"""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = jobs[job_id]
    if job.get('status') == 'processing':
        elapsed = time.time() - job.get('start_time', time.time())
        job['elapsed'] = round(elapsed, 1)
    
    return jsonify(job)

@app.route('/file/<filename>')
def serve_file(filename):
    """Serve the MP3 file"""
    safe_name = secure_filename(filename)
    file_path = f'/app/downloads/{safe_name}'
    
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    
    return jsonify({'error': 'File not found'}), 404

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

@app.route('/')
def home():
    return jsonify({
        'message': 'YouTube Audio API - WORKING VERSION',
        'endpoints': {
            'download': '/download?url=YOUTUBE_URL',
            'status': '/status/JOB_ID', 
            'file': '/file/FILENAME.mp3',
            'health': '/health'
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
