from flask import Flask, request, jsonify
import yt_dlp
import os

app = Flask(__name__)

ydl_opts_fast = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'outtmpl': '/tmp/%(title)s.%(ext)s',
    'noplaylist': True,
    'socket_timeout': 20,
    'retries': 2,
    'fragment_retries': 2,
    'extract_flat': False,
    'no_warnings': True,
}

@app.route('/fast-audio', methods=['GET'])
def fast_audio():
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts_fast) as ydl:
            info = ydl.extract_info(url, download=True)
            
            return jsonify({
                "status": "success", 
                "title": info.get('title', ''),
                "message": "Audio downloaded"
            })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/')
def home():
    return jsonify({"message": "YT-DLP API is running!", "status": "success"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
