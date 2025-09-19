from flask import Flask, request, jsonify, send_file
import yt_dlp
import os
import time
import uuid
from werkzeug.utils import secure_filename
import glob

app = Flask(__name__)

# Create directories if they don't exist
os.makedirs('/app/downloads', exist_ok=True)

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
    'retries': 10,
    'fragment_retries': 10,
    'ignoreerrors': True,
    'cookiefile': 'cookies.txt',
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'throttled_rate': '1M',
    'sleep_interval': 2,
}

@app.route('/fast-audio', methods=['GET'])
def fast_audio():
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "No URL provided. Use ?url=YOUTUBE_URL"}), 400
    
    try:
        start_time = time.time()
        
        with yt_dlp.YoutubeDL(ydl_opts_fast) as ydl:
            info = ydl.extract_info(url, download=True)
            
            duration = time.time() - start_time
            
            # Get the actual downloaded filename
            original_filename = ydl.prepare_filename(info)
            mp3_filename = original_filename.rsplit('.', 1)[0] + '.mp3'
            base_name = os.path.basename(mp3_filename)
            safe_name = secure_filename(base_name)
            
            return jsonify({
                "status": "success", 
                "title": info.get('title', 'Unknown Title'),
                "duration": info.get('duration', 0),
                "download_time": round(duration, 2),
                "download_url": f"https://yt-dlp-munax.koyeb.app/download-file/{safe_name}",
                "original_filename": base_name,
                "safe_filename": safe_name,
                "message": "Audio downloaded successfully as MP3"
            })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/download-file/<filename>')
def download_file(filename):
    try:
        safe_filename = secure_filename(filename)
        file_path = f"/app/downloads/{safe_filename}"
        
        # Check if file exists with secure filename
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True, download_name=safe_filename)
        
        # If not found, search for files with original names
        all_files = glob.glob('/app/downloads/*')
        for actual_file in all_files:
            actual_filename = os.path.basename(actual_file)
            if secure_filename(actual_filename) == safe_filename:
                return send_file(actual_file, as_attachment=True, download_name=safe_filename)
        
        return jsonify({"error": "File not found", "filename": filename}), 404
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Cleanup function to remove old files
@app.route('/cleanup')
def cleanup_files():
    try:
        files = glob.glob('/app/downloads/*')
        deleted_count = 0
        for file_path in files:
            if os.path.isfile(file_path) and time.time() - os.path.getctime(file_path) > 3600:
                os.remove(file_path)
                deleted_count += 1
        return jsonify({
            "message": "Cleanup completed", 
            "deleted_files": deleted_count,
            "remaining_files": len(glob.glob('/app/downloads/*'))
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/')
def home():
    return jsonify({
        "message": "Munax-API is running successfully!",
        "status": "active",
        "endpoints": {
            "audio_download": "/fast-audio?url=YOUTUBE_URL",
            "file_download": "/download-file/FILENAME.mp3",
            "cleanup": "/cleanup"
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
