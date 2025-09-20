from flask import Flask, request, jsonify, send_file
import subprocess
import os
import uuid
import time
import threading
from werkzeug.utils import secure_filename
import random

app = Flask(__name__)

# Create directories
os.makedirs('/app/downloads', exist_ok=True)

# Global storage for jobs
jobs = {}

# User agents for rotation
USER_AGENTS = [
    'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15',
    'Mozilla/5.0 (Android 13; Mobile; rv:109.0) Gecko/109.0 Firefox/109.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
]

def nuclear_download(url, job_id):
    """Multiple fallback methods - ONE WILL WORK"""
    try:
        jobs[job_id] = {'status': 'processing', 'start_time': time.time()}
        
        file_id = str(uuid.uuid4())[:8]
        output_file = f"/app/downloads/audio_{file_id}"
        
        # METHOD 1: Basic yt-dlp
        methods = [
            # Try 1: Simple
            ['yt-dlp', '-x', '--audio-format', 'mp3', '--no-warnings', '--quiet', '-o', f'{output_file}.%(ext)s', url],
            
            # Try 2: With user agent
            ['yt-dlp', '-x', '--audio-format', 'mp3', '--user-agent', random.choice(USER_AGENTS), '--no-warnings', '--quiet', '-o', f'{output_file}.%(ext)s', url],
            
            # Try 3: Mobile simulation
            ['yt-dlp', '-x', '--audio-format', 'mp3', '--user-agent', USER_AGENTS[0], '--add-header', 'Accept-Language: en-US,en;q=0.9', '--no-warnings', '--quiet', '-o', f'{output_file}.%(ext)s', url],
            
            # Try 4: Just get any audio
            ['yt-dlp', '--format', 'bestaudio', '--no-warnings', '--quiet', '-o', f'{output_file}.%(ext)s', url],
            
            # Try 5: Worst quality (most likely to work)
            ['yt-dlp', '--format', 'worstaudio', '--no-warnings', '--quiet', '-o', f'{output_file}.%(ext)s', url]
        ]
        
        success = False
        final_file = None
        
        for i, cmd in enumerate(methods, 1):
            try:
                print(f"Trying method {i}: {' '.join(cmd[:3])}...")
                
                result = subprocess.run(cmd, timeout=120, capture_output=True, text=True)
                
                # Check for any file that was created
                possible_files = [
                    f'{output_file}.mp3',
                    f'{output_file}.m4a', 
                    f'{output_file}.webm',
                    f'{output_file}.opus'
                ]
                
                for possible_file in possible_files:
                    if os.path.exists(possible_file):
                        final_file = possible_file
                        success = True
                        print(f"SUCCESS with method {i}! File: {final_file}")
                        break
                
                if success:
                    break
                    
            except Exception as e:
                print(f"Method {i} failed: {e}")
                continue
        
        if success and final_file:
            filename = os.path.basename(final_file)
            jobs[job_id] = {
                'status': 'completed',
                'filename': filename,
                'download_url': f'https://yt-dlp-munax.koyeb.app/file/{filename}',
                'method_used': i
            }
        else:
            jobs[job_id] = {'status': 'failed', 'error': 'All 5 methods failed - YouTube is blocking everything'}
            
    except Exception as e:
        jobs[job_id] = {'status': 'failed', 'error': f'Fatal error: {str(e)}'}

@app.route('/download')
def download():
    """Nuclear download endpoint"""
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    job_id = str(uuid.uuid4())
    
    # Start background download with multiple methods
    thread = threading.Thread(target=nuclear_download, args=(url, job_id))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'job_id': job_id,
        'status': 'processing',
        'check_url': f'https://yt-dlp-munax.koyeb.app/status/{job_id}',
        'message': 'Trying 5 different methods...'
    })

@app.route('/status/<job_id>')
def status(job_id):
    """Check job status"""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = jobs[job_id].copy()
    if job.get('status') == 'processing':
        elapsed = time.time() - job.get('start_time', time.time())
        job['elapsed'] = round(elapsed, 1)
    
    return jsonify(job)

@app.route('/file/<filename>')
def serve_file(filename):
    """Serve any audio file"""
    safe_name = secure_filename(filename)
    file_path = f'/app/downloads/{safe_name}'
    
    if os.path.exists(file_path):
        # Determine mimetype based on extension
        if filename.endswith('.mp3'):
            mimetype = 'audio/mpeg'
        elif filename.endswith('.m4a'):
            mimetype = 'audio/mp4'
        elif filename.endswith('.webm'):
            mimetype = 'audio/webm'
        else:
            mimetype = 'audio/mpeg'
            
        return send_file(file_path, as_attachment=True, mimetype=mimetype)
    
    return jsonify({'error': 'File not found'}), 404

@app.route('/debug/<job_id>')
def debug_job(job_id):
    """Debug what happened"""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    # List all files in downloads directory
    files = []
    try:
        for f in os.listdir('/app/downloads'):
            files.append(f)
    except:
        pass
    
    return jsonify({
        'job': jobs[job_id],
        'all_files': files,
        'directory_exists': os.path.exists('/app/downloads')
    })

@app.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'yt_dlp_available': True,
        'methods': '5 fallback methods'
    })

@app.route('/')
def home():
    return jsonify({
        'message': 'YouTube Audio API - NUCLEAR VERSION',
        'version': '5.0 - Multiple Fallbacks',
        'methods': '5 different download strategies',
        'endpoints': {
            'download': '/download?url=YOUTUBE_URL',
            'status': '/status/JOB_ID', 
            'debug': '/debug/JOB_ID',
            'file': '/file/FILENAME',
            'health': '/health'
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=True)
