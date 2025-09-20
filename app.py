from flask import Flask, request, jsonify, send_file
import os
import time
import uuid
import glob
import subprocess
import json
import random
import threading
import re
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Create directories
os.makedirs('/app/downloads', exist_ok=True)
os.makedirs('/app/metadata', exist_ok=True)

# User agents for rotation
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1'
]

# Rate limiting
request_timestamps = []
MAX_REQUESTS_PER_MINUTE = 20

def rate_limit_check():
    """Prevent API abuse"""
    global request_timestamps
    current_time = time.time()
    request_timestamps = [ts for ts in request_timestamps if current_time - ts < 60]
    if len(request_timestamps) >= MAX_REQUESTS_PER_MINUTE:
        return False
    request_timestamps.append(current_time)
    return True

def extract_video_id(url):
    """Extract YouTube video ID"""
    try:
        patterns = [
            r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
            r'youtu\.be\/([0-9A-Za-z_-]{11})'
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match and len(match.group(1)) == 11:
                return match.group(1)
        return None
    except:
        return None

def auto_cleanup():
    """Auto-cleanup every hour"""
    while True:
        try:
            time.sleep(3600)
            current_time = time.time()
            for file_path in glob.glob('/app/downloads/*'):
                if current_time - os.path.getctime(file_path) > 7200:
                    try:
                        os.remove(file_path)
                        meta_path = f"/app/metadata/{os.path.basename(file_path)}.json"
                        if os.path.exists(meta_path):
                            os.remove(meta_path)
                    except:
                        pass
        except:
            time.sleep(300)

# Start cleanup thread
cleanup_thread = threading.Thread(target=auto_cleanup)
cleanup_thread.daemon = True
cleanup_thread.start()

def get_video_info_safe(url):
    """Safe video info extraction"""
    try:
        video_id = extract_video_id(url)
        if not video_id:
            return {'success': False, 'error': 'Invalid YouTube URL'}
        
        user_agent = random.choice(USER_AGENTS)
        
        cmd = [
            'yt-dlp',
            '--dump-json',
            '--no-warnings',
            '--quiet',
            '--user-agent', user_agent,
            url
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            info = json.loads(result.stdout)
            return {
                'title': info.get('title', 'Audio'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg'),
                'uploader': info.get('uploader', 'Unknown Artist'),
                'video_id': video_id,
                'success': True
            }
        return {'success': False, 'error': 'Could not get video info'}
    except:
        return {'success': False, 'error': 'Info extraction failed'}

def safe_download(url):
    """Simplified reliable download"""
    try:
        file_id = str(uuid.uuid4())[:8]
        output_path = f"/app/downloads/audio_{file_id}.mp3"
        
        # SIMPLE & RELIABLE command
        cmd = [
            'yt-dlp',
            '-x', 
            '--audio-format', 'mp3',
            '--audio-quality', '192K',
            '--no-warnings',
            '--quiet',
            '--extractor-retries', '3',
            '--fragment-retries', '3',
            '-o', output_path,
            url
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        # DEBUG: Log the result
        print(f"Download command executed. Return code: {result.returncode}")
        if result.stderr:
            print(f"Error output: {result.stderr}")
        if result.stdout:
            print(f"Standard output: {result.stdout}")
        
        if result.returncode == 0 and os.path.exists(output_path):
            return {
                'success': True,
                'file_path': output_path,
                'filename': os.path.basename(output_path),
                'file_size': os.path.getsize(output_path)
            }
        return {'success': False, 'error': result.stderr or 'Download failed'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

# ================== VERIFICATION ENDPOINTS ================== #

@app.route('/version')
def version_info():
    """Check yt-dlp version"""
    try:
        result = subprocess.run(['yt-dlp', '--version'], capture_output=True, text=True)
        return jsonify({
            "yt_dlp_version": result.stdout.strip(),
            "status": "success"
        })
    except:
        return jsonify({"error": "Version check failed"}), 500

@app.route('/verify')
def verify_system():
    """Comprehensive system verification"""
    tests = []
    
    # Test yt-dlp
    try:
        version_result = subprocess.run(['yt-dlp', '--version'], capture_output=True, text=True)
        tests.append({
            "test": "yt-dlp_version",
            "status": "passed" if version_result.returncode == 0 else "failed",
            "version": version_result.stdout.strip() if version_result.returncode == 0 else "unknown"
        })
    except:
        tests.append({"test": "yt-dlp_version", "status": "failed"})
    
    # Test FFmpeg
    try:
        ffmpeg_result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        tests.append({
            "test": "ffmpeg_available",
            "status": "passed" if ffmpeg_result.returncode == 0 else "failed"
        })
    except:
        tests.append({"test": "ffmpeg_available", "status": "failed"})
    
    # Test directories
    downloads_writable = os.access('/app/downloads', os.W_OK)
    tests.append({
        "test": "directory_permissions",
        "status": "passed" if downloads_writable else "failed"
    })
    
    all_passed = all(test['status'] == 'passed' for test in tests)
    return jsonify({
        "status": "success" if all_passed else "degraded",
        "tests": tests
    })

@app.route('/debug-download')
def debug_download():
    """Debug download with detailed output"""
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
    cmd = [
        'yt-dlp',
        '-x',
        '--audio-format', 'mp3',
        '--audio-quality', '192K',
        '--verbose',  # Verbose output for debugging
        '-o', '/app/downloads/debug_test.%(ext)s',
        test_url
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return jsonify({
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": result.returncode == 0
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/test-download')
def test_download():
    """Test download functionality"""
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
    try:
        download_result = safe_download(test_url)
        
        if download_result['success']:
            # Clean up test file
            try:
                os.remove(download_result['file_path'])
            except:
                pass
                
            return jsonify({
                "status": "success",
                "message": "Download test passed successfully"
            })
        else:
            return jsonify({
                "status": "failed",
                "error": download_result.get('error', 'Download failed'),
                "message": "Download test failed - check debug endpoint"
            }), 500
            
    except Exception as e:
        return jsonify({
            "status": "failed",
            "error": str(e)
        }), 500

# ================== MAIN ENDPOINTS ================== #

@app.before_request
def before_request():
    """Rate limiting"""
    if not rate_limit_check():
        return jsonify({"error": "Rate limit exceeded", "retry_after": "60 seconds"}), 429

@app.route('/download', methods=['GET'])
def download_audio():
    """Main download endpoint"""
    if not rate_limit_check():
        return jsonify({"error": "Rate limit exceeded"}), 429
    
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "URL parameter required"}), 400
    
    if 'youtube.com/' not in url and 'youtu.be/' not in url:
        return jsonify({"error": "Only YouTube URLs supported"}), 400
    
    try:
        start_time = time.time()
        video_info = get_video_info_safe(url)
        download_result = safe_download(url)
        
        if download_result['success']:
            download_time = round(time.time() - start_time, 2)
            
            response_data = {
                "status": "completed",
                "download_url": f"https://yt-dlp-munax.koyeb.app/file/{download_result['filename']}",
                "filename": download_result['filename'],
                "download_time": download_time,
                "file_size_mb": round(download_result.get('file_size', 0) / 1024 / 1024, 2),
                "metadata": {
                    "title": video_info.get('title', 'Audio') if video_info.get('success') else 'Audio',
                    "duration": video_info.get('duration', 0) if video_info.get('success') else 0,
                    "artist": video_info.get('uploader', 'Unknown Artist') if video_info.get('success') else 'Unknown Artist',
                    "thumbnail": video_info.get('thumbnail', '') if video_info.get('success') else ''
                }
            }
            
            try:
                metadata_path = f"/app/metadata/{download_result['filename']}.json"
                with open(metadata_path, 'w') as f:
                    json.dump(response_data, f)
            except:
                pass
                
            return jsonify(response_data)
        else:
            return jsonify({
                "status": "failed",
                "error": download_result.get('error', 'Download failed')
            }), 500
            
    except Exception as e:
        return jsonify({
            "status": "failed",
            "error": "Service temporarily unavailable"
        }), 500

@app.route('/file/<filename>')
def serve_file(filename):
    """Serve downloaded file"""
    try:
        safe_name = secure_filename(filename)
        file_path = f"/app/downloads/{safe_name}"
        
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True, download_name=safe_name)
        return jsonify({"error": "File not found"}), 404
    except:
        return jsonify({"error": "File service error"}), 500

@app.route('/info', methods=['GET'])
def get_info():
    """Get video info without downloading"""
    if not rate_limit_check():
        return jsonify({"error": "Rate limit exceeded"}), 429
    
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "URL parameter required"}), 400
    
    info = get_video_info_safe(url)
    if info.get('success'):
        return jsonify({"status": "success", "data": info})
    else:
        return jsonify({
            "status": "failed", 
            "error": info.get('error', 'Could not get video info')
        }), 500

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": time.time(),
        "service": "yt-audio-api"
    })

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
            "message": "Cleanup completed",
            "deleted_files": deleted_files
        })
    except:
        return jsonify({"error": "Cleanup failed"}), 500

@app.route('/')
def home():
    """API documentation"""
    return jsonify({
        "message": "🎵 YouTube Audio Downloader API",
        "status": "active",
        "endpoints": {
            "download": "/download?url=YOUTUBE_URL",
            "info": "/info?url=YOUTUBE_URL",
            "file_download": "/file/FILENAME.mp3",
            "health": "/health",
            "version": "/version",
            "verify": "/verify",
            "debug": "/debug-download",
            "test": "/test-download",
            "cleanup": "/cleanup (POST)"
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    print(f"🚀 Starting YouTube Audio API on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
