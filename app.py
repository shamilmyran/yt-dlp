from flask import Flask, request, jsonify
import yt_dlp
import os
import tempfile
from urllib.parse import urlparse

app = Flask(__name__)

@app.route('/audio', methods=['GET'])
def download_audio():
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    
    try:
        # Create temp directory for downloads
        temp_dir = tempfile.mkdtemp()
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': f'{temp_dir}/%(title)s.%(ext)s',
            'noplaylist': True,
            'extractaudio': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            return jsonify({
                "status": "success", 
                "title": info.get('title', ''),
                "duration": info.get('duration', 0),
                "uploader": info.get('uploader', '')
            })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/video', methods=['GET'])
def download_video():
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    
    try:
        temp_dir = tempfile.mkdtemp()
        
        ydl_opts = {
            'format': 'best[height<=720]',
            'outtmpl': f'{temp_dir}/%(title)s.%(ext)s',
            'noplaylist': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            return jsonify({
                "status": "success", 
                "title": info.get('title', ''),
                "duration": info.get('duration', 0)
            })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/info', methods=['GET'])
def get_info():
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    
    try:
        ydl_opts = {'quiet': True}
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            return jsonify({
                "title": info.get('title', ''),
                "duration": info.get('duration', 0),
                "uploader": info.get('uploader', ''),
                "view_count": info.get('view_count', 0),
                "upload_date": info.get('upload_date', '')
            })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "YouTube Downloader API"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
