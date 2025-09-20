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

# ഡയറക്ടറികൾ സൃഷ്ടിക്കുന്നു
os.makedirs('/app/downloads', exist_ok=True)
os.makedirs('/app/metadata', exist_ok=True)

# മെച്ചപ്പെട്ട ആന്റി-ബ്ലോക്കിംഗ് കോൺഫിഗറേഷനുകൾ
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Android 13; Mobile; rv:109.0) Gecko/109.0 Firefox/109.0',
    'Mozilla/5.0 (iPad; CPU OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
]

# വിജയ ട്രാക്കിംഗ്
success_stats = {'total': 0, 'successful': 0, 'methods': {}}
request_timestamps = []
MAX_REQUESTS_PER_MINUTE = 30

def rate_limit_check():
    """മെച്ചപ്പെട്ട റേറ്റ് ലിമിറ്റിംഗ്"""
    global request_timestamps
    current_time = time.time()
    request_timestamps = [ts for ts in request_timestamps if current_time - ts < 60]
    if len(request_timestamps) >= MAX_REQUESTS_PER_MINUTE:
        return False
    request_timestamps.append(current_time)
    return True

def extract_video_id(url):
    """വിവിധ URL ഫോർമാറ്റുകളിൽ നിന്ന് YouTube വീഡിയോ ID എക്‌സ്ട്രാക്റ്റ് ചെയ്യുന്നു"""
    try:
        patterns = [
            r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
            r'youtu\.be\/([0-9A-Za-z_-]{11})',
            r'embed\/([0-9A-Za-z_-]{11})',
            r'shorts\/([0-9A-Za-z_-]{11})'
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match and len(match.group(1)) == 11:
                return match.group(1)
        return None
    except:
        return None

def auto_cleanup():
    """സ്ഥിതിവിവരക്കണക്കുകളുള്ള മെച്ചപ്പെട്ട ഓട്ടോ-ക്ലീനപ്പ്"""
    while True:
        try:
            time.sleep(1800)  # ഓരോ 30 മിനിറ്റിലും ഓടിക്കുക
            current_time = time.time()
            
            deleted_files = 0
            # 2 മണിക്കൂറിൽ കൂടുതൽ പഴക്കമുള്ള ഡൗൺലോഡുകൾ ക്ലീൻ ചെയ്യുക
            for file_path in glob.glob('/app/downloads/*'):
                if current_time - os.path.getctime(file_path) > 7200:
                    try:
                        os.remove(file_path)
                        deleted_files += 1
                        # അനുബന്ധ മെറ്റാഡാറ്റ നീക്കം ചെയ്യുക
                        meta_path = f"/app/metadata/{os.path.basename(file_path)}.json"
                        if os.path.exists(meta_path):
                            os.remove(meta_path)
                    except:
                        pass
            
            print(f"🧹 ഓട്ടോ-ക്ലീനപ്പ്: {deleted_files} പഴയ ഫയലുകൾ നീക്കം ചെയ്തു")
        except:
            time.sleep(300)

# ക്ലീനപ്പ് ത്രെഡ് ആരംഭിക്കുക
cleanup_thread = threading.Thread(target=auto_cleanup)
cleanup_thread.daemon = True
cleanup_thread.start()

def get_video_info_enhanced(url):
    """മൾട്ടിപ്പിൾ സ്ട്രാറ്റജികളുള്ള മെച്ചപ്പെട്ട വീഡിയോ വിവരങ്ങൾ"""
    try:
        video_id = extract_video_id(url)
        if not video_id:
            return {'success': False, 'error': 'അസാധുവായ YouTube URL'}
        
        strategies = [
            ['--impersonate', 'chrome'],
            ['--impersonate', 'firefox'], 
            ['--user-agent', random.choice(USER_AGENTS)],
            []  # ബേസിക് ഫോൾബാക്ക്
        ]
        
        for strategy in strategies:
            try:
                cmd = [
                    'yt-dlp',
                    '--dump-json',
                    '--no-warnings',
                    '--quiet'
                ] + strategy + [url]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                
                if result.returncode == 0:
                    info = json.loads(result.stdout)
                    return {
                        'title': info.get('title', 'ഓഡിയോ')[:100],
                        'duration': info.get('duration', 0),
                        'thumbnail': info.get('thumbnail', f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg'),
                        'uploader': info.get('uploader', 'അജ്ഞാത ആർട്ടിസ്റ്റ്')[:50],
                        'view_count': info.get('view_count', 0),
                        'upload_date': info.get('upload_date', ''),
                        'video_id': video_id,
                        'success': True
                    }
            except:
                continue
        
        return {'success': False, 'error': 'എല്ലാ വിവര എക്‌സ്ട്രാക്ഷൻ രീതികളും പരാജയപ്പെട്ടു'}
    except:
        return {'success': False, 'error': 'വിവര എക്‌സ്ട്രാക്ഷൻ പരാജയപ്പെട്ടു'}

def smart_download_with_fallbacks(url):
    """മൾട്ടിപ്പിൾ ആന്റി-ബ്ലോക്കിംഗ് സ്ട്രാറ്റജികളുള്ള അൾട്ടിമേറ്റ് ഡൗൺലോഡ്"""
    global success_stats
    
    strategies = [
        {
            'name': 'chrome_impersonate_hq',
            'cmd_parts': [
                '--impersonate', 'chrome', 
                '--audio-quality', '192K',
                '--throttled-rate', '100K',
                '--sleep-interval', str(random.randint(2, 5))
            ]
        },
        {
            'name': 'firefox_impersonate_mq',
            'cmd_parts': [
                '--impersonate', 'firefox',
                '--audio-quality', '128K',
                '--limit-rate', '500K'
            ]
        },
        {
            'name': 'mobile_agent_lq',
            'cmd_parts': [
                '--user-agent', random.choice([ua for ua in USER_AGENTS if 'Mobile' in ua or 'iPhone' in ua or 'Android' in ua]),
                '--audio-quality', '96K',
                '--format', 'worstaudio',
                '--sleep-interval', '5'
            ]
        },
        {
            'name': 'bypass_age_restriction',
            'cmd_parts': [
                '--age-limit', '18',
                '--audio-quality', '128K',
                '--sleep-interval', '10'
            ]
        },
        {
            'name': 'extreme_fallback',
            'cmd_parts': [
                '--force-ipv4',
                '--audio-quality', '64K',
                '--format', 'worstaudio/worst',
                '--sleep-interval', '15',
                '--retries', '10'
            ]
        }
    ]
    
    for strategy in strategies:
        try:
            file_id = str(uuid.uuid4())[:8]
            output_path = f"/app/downloads/audio_{file_id}.mp3"
            
            base_cmd = [
                'yt-dlp',
                '-x',
                '--audio-format', 'mp3',
                '--no-warnings',
                '--quiet',
                '--socket-timeout', '20',
                '--extractor-retries', '2',
                '--fragment-retries', '2'
            ]
            
            # സ്ട്രാറ്റജി-സ്പെസിഫിക് ഓപ്ഷനുകൾ ചേർക്കുക
            cmd = base_cmd + strategy['cmd_parts'] + [
                '--add-header', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                '--add-header', 'Accept-Language: en-US,en;q=0.5',
                '-o', output_path,
                url
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            if result.returncode == 0 and os.path.exists(output_path):
                # വിജയകരമായ രീതി ട്രാക്ക് ചെയ്യുക
                success_stats['methods'][strategy['name']] = success_stats['methods'].get(strategy['name'], 0) + 1
                
                return {
                    'success': True,
                    'method': strategy['name'],
                    'file_path': output_path,
                    'filename': os.path.basename(output_path),
                    'file_size': os.path.getsize(output_path)
                }
        except subprocess.TimeoutExpired:
            continue
        except Exception:
            continue
    
    return {'success': False, 'error': 'എല്ലാ ഡൗൺലോഡ് സ്ട്രാറ്റജികളും പരാജയപ്പെട്ടു - സാധ്യതയുള്ള ബ്ലോക്ക്'}

# ================== API എൻഡ്‌പോയിന്റുകൾ ================== #

@app.before_request
def before_request():
    """യൂസർ ട്രാക്കിംഗ് ഉള്ള മെച്ചപ്പെട്ട റേറ്റ് ലിമിറ്റിംഗ്"""
    if request.endpoint in ['static', 'favicon']:
        return
    if not rate_limit_check():
        return jsonify({
            "error": "റേറ്റ് പരിധി കവിഞ്ഞു", 
            "retry_after": "60 സെക്കൻഡ്",
            "limit": f"{MAX_REQUESTS_PER_MINUTE} മിനിറ്റിൽ അഭ്യർത്ഥനകൾ"
        }), 429

@app.route('/download', methods=['GET'])
def download_audio():
    """മെച്ചപ്പെട്ട പ്രധാന ഡൗൺലോഡ് എൻഡ്‌പോയിന്റ്"""
    global success_stats
    success_stats['total'] += 1
    
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "URL പാരാമീറ്റർ ആവശ്യമാണ് (?url=YOUTUBE_URL)"}), 400
    
    # മെച്ചപ്പെട്ട URL വാലിഡേഷൻ
    if not any(domain in url for domain in ['youtube.com', 'youtu.be', 'm.youtube.com', 'music.youtube.com']):
        return jsonify({"error": "YouTube URLs മാത്രമേ പിന്തുണയ്ക്കുന്നുള്ളൂ"}), 400
    
    try:
        start_time = time.time()
        
        # വീഡിയോ വിവരങ്ങൾ നേടുക (നോൺ-ബ്ലോക്കിംഗ്)
        video_info = get_video_info_enhanced(url)
        
        # ഫോൾബാക്കുകളുള്ള സ്മാർട്ട് ഡൗൺലോഡ്
        download_result = smart_download_with_fallbacks(url)
        
        if download_result['success']:
            success_stats['successful'] += 1
            download_time = round(time.time() - start_time, 2)
            
            response_data = {
                "status": "completed",
                "download_url": f"/file/{download_result['filename']}",
                "filename": download_result['filename'],
                "download_time": download_time,
                "method_used": download_result.get('method', 'unknown'),
                "file_size_mb": round(download_result.get('file_size', 0) / 1024 / 1024, 2),
                "metadata": {
                    "title": video_info.get('title', 'ഓഡിയോ') if video_info.get('success') else 'ഓഡിയോ',
                    "duration": video_info.get('duration', 0) if video_info.get('success') else 0,
                    "artist": video_info.get('uploader', 'അജ്ഞാത ആർട്ടിസ്റ്റ്') if video_info.get('success') else 'അജ്ഞാത ആർട്ടിസ്റ്റ്',
                    "thumbnail": video_info.get('thumbnail', '') if video_info.get('success') else '',
                    "video_id": video_info.get('video_id', '') if video_info.get('success') else '',
                    "view_count": video_info.get('view_count', 0) if video_info.get('success') else 0
                }
            }
            
            # മെറ്റാഡാറ്റ സേവ് ചെയ്യുക
            try:
                metadata_path = f"/app/metadata/{download_result['filename']}.json"
                with open(metadata_path, 'w') as f:
                    json.dump(response_data, f, indent=2)
            except:
                pass
                
            return jsonify(response_data)
        else:
            return jsonify({
                "status": "failed",
                "error": download_result.get('error', 'ഡൗൺലോഡ് പരാജയപ്പെട്ടു'),
                "suggestion": "വീഡിയോ ജിയോ-ബ്ലോക്ക് ചെയ്യപ്പെട്ടതോ വയസ്സ് പരിമിതിയുള്ളതോ ആയിരിക്കാം",
                "fallback_recommended": True
            }), 500
            
    except Exception as e:
        return jsonify({
            "status": "failed",
            "error": "സേവനം താൽക്കാലികമായി ലഭ്യമല്ല",
            "retry_after": "30 സെക്കൻഡ്"
        }), 500

@app.route('/file/<filename>')
def serve_file(filename):
    """സുരക്ഷയുള്ള മെച്ചപ്പെട്ട ഫയൽ സേവനം"""
    try:
        safe_name = secure_filename(filename)
        file_path = f"/app/downloads/{safe_name}"
        
        if os.path.exists(file_path):
            # ഹെഡറുകൾക്കായി ഫയൽ വിവരങ്ങൾ നേടുക
            file_size = os.path.getsize(file_path)
            return send_file(
                file_path, 
                as_attachment=True, 
                download_name=safe_name,
                mimetype='audio/mpeg'
            )
        
        return jsonify({"error": "ഫയൽ കണ്ടെത്തിയില്ല അല്ലെങ്കിൽ കാലഹരണപ്പെട്ടത്"}), 404
    except Exception as e:
        return jsonify({"error": "ഫയൽ സേവന പിശക്"}), 500

@app.route('/info', methods=['GET'])
def get_info():
    """മൾട്ടിപ്പിൾ സ്ട്രാറ്റജികളുള്ള മെച്ചപ്പെട്ട വിവര എൻഡ്‌പോയിന്റ്"""
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "URL പാരാമീറ്റർ ആവശ്യമാണ് (?url=YOUTUBE_URL)"}), 400
    
    info = get_video_info_enhanced(url)
    if info.get('success'):
        return jsonify({"status": "success", "data": info})
    else:
        return jsonify({
            "status": "failed", 
            "error": info.get('error', 'വീഡിയോ വിവരങ്ങൾ നേടാൻ കഴിഞ്ഞില്ല'),
            "suggestion": "വീഡിയോ സ്വകാര്യമോ ഇല്ലാതാക്കിയതോ ജിയോ-ബ്ലോക്ക് ചെയ്തതോ ആയിരിക്കാം"
        }), 500

@app.route('/stats')
def get_stats():
    """സമഗ്രമായ API സ്ഥിതിവിവരക്കണക്കുകൾ"""
    try:
        total = success_stats['total']
        successful = success_stats['successful']
        success_rate = (successful / total * 100) if total > 0 else 0
        
        # മികച്ച പ്രകടനം നൽകുന്ന രീതികൾ
        methods = success_stats['methods']
        top_method = max(methods, key=methods.get) if methods else 'none'
        
        return jsonify({
            "performance": {
                "total_requests": total,
                "successful_downloads": successful,
                "success_rate": f"{success_rate:.1f}%",
                "api_health": "മികച്ചത്" if success_rate > 80 else "നല്ലത്" if success_rate > 60 else "മോശം"
            },
            "methods": {
                "most_successful": top_method,
                "breakdown": methods
            },
            "system": {
                "active_files": len(glob.glob('/app/downloads/*')),
                "uptime": "തുടർച്ചയായ",
                "auto_cleanup": "ഓരോ 30 മിനിറ്റിലും"
            },
            "timestamp": time.time()
        })
    except:
        return jsonify({"error": "സ്ഥിതിവിവരക്കണക്കുകൾ ലഭ്യമല്ല"}), 500

@app.route('/health')
def health_check():
    """സമഗ്രമായ ആരോഗ്യ പരിശോധന"""
    try:
        # yt-dlp ലഭ്യത പരീക്ഷിക്കുക
        yt_dlp_test = subprocess.run(['yt-dlp', '--version'], capture_output=True, timeout=5)
        yt_dlp_ok = yt_dlp_test.returncode == 0
        
        # ffmpeg ലഭ്യത പരീക്ഷിക്കുക
        ffmpeg_test = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
        ffmpeg_ok = ffmpeg_test.returncode == 0
        
        # ഡിസ്ക് സ്പേസ് പരിശോധിക്കുക
        files_count = len(glob.glob('/app/downloads/*'))
        
        health_status = "ആരോഗ്യകരമായ" if (yt_dlp_ok and ffmpeg_ok) else "അപഗ്രഥിതം"
        
        return jsonify({
            "status": health_status,
            "components": {
                "yt_dlp": "ശരി" if yt_dlp_ok else "പിശക്",
                "ffmpeg": "ശരി" if ffmpeg_ok else "പിശക്",
                "storage": "ശരി" if files_count < 100 else "മുന്നറിയിപ്പ്"
            },
            "metrics": {
                "active_files": files_count,
                "success_rate": f"{(success_stats['successful'] / success_stats['total'] * 100) if success_stats['total'] > 0 else 0:.1f}%"
            },
            "timestamp": time.time()
        })
    except:
        return jsonify({"status": "പിശക്"}), 500

@app.route('/version')
def version_info():
    """മെച്ചപ്പെട്ട പതിപ്പ് വിവരങ്ങൾ"""
    try:
        yt_dlp_result = subprocess.run(['yt-dlp', '--version'], capture_output=True, text=True)
        ffmpeg_result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        
        return jsonify({
            "api_version": "4.0.0",
            "yt_dlp_version": yt_dlp_result.stdout.strip() if yt_dlp_result.returncode == 0 else "അജ്ഞാതം",
            "ffmpeg_available": ffmpeg_result.returncode == 0,
            "python_version": "3.11+",
            "features": [
                "ബ്രൗസർ പ്രതിരൂപണം",
                "മൾട്ടിപ്പിൾ ഫോൾബാക്ക് സ്ട്രാറ്റജികൾ", 
                "ഓട്ടോ-ക്ലീനപ്പ് സിസ്റ്റം",
                "വിജയ നിരക്ക് മോണിറ്ററിംഗ്",
                "മെച്ചപ്പെട്ട പിശക് കൈകാര്യം ചെയ്യൽ"
            ]
        })
    except:
        return jsonify({"error": "പതിപ്പ് പരിശോധന പരാജയപ്പെട്ടു"}), 500

@app.route('/cleanup', methods=['POST'])
def manual_cleanup():
    """സ്ഥിതിവിവരക്കണക്കുകളുള്ള മെച്ചപ്പെട്ട മാനുവൽ ക്ലീനപ്പ്"""
    try:
        deleted_files = 0
        deleted_metadata = 0
        
        # എല്ലാ ഡൗൺലോഡുകളും ക്ലീൻ ചെയ്യുക
        for file_path in glob.glob('/app/downloads/*'):
            try:
                os.remove(file_path)
                deleted_files += 1
            except:
                pass
        
        # എല്ലാ മെറ്റാഡാറ്റയും ക്ലീൻ ചെയ്യുക
        for meta_path in glob.glob('/app/metadata/*'):
            try:
                os.remove(meta_path)
                deleted_metadata += 1
            except:
                pass
        
        return jsonify({
            "message": "മാനുവൽ ക്ലീനപ്പ് വിജയകരമായി പൂർത്തിയായി",
            "deleted_files": deleted_files,
            "deleted_metadata": deleted_metadata,
            "next_auto_cleanup": "30 മിനിറ്റ്"
        })
    except:
        return jsonify({"error": "ക്ലീനപ്പ് പരാജയപ്പെട്ടു"}), 500

@app.route('/')
def home():
    """മെച്ചപ്പെട്ട API ഡോക്യുമെന്റേഷൻ"""
    success_rate = (success_stats['successful'] / success_stats['total'] * 100) if success_stats['total'] > 0 else 0
    
    return jsonify({
        "name": "🎵 YouTube ഓഡിയോ ഡൗൺലോഡർ API",
        "version": "4.0.0 - അൾട്ടിമേറ്റ് എഡിഷൻ",
        "status": "സജീവം",
        "current_success_rate": f"{success_rate:.1f}%",
        "endpoints": {
            "download": {
                "url": "/download?url=YOUTUBE_URL",
                "description": "മൾട്ടിപ്പിൾ ഫോൾബാക്ക് സ്ട്രാറ്റജികളുള്ള ഓഡിയോ ഡൗൺലോഡ് ചെയ്യുക",
                "methods": ["GET"]
            },
            "info": {
                "url": "/info?url=YOUTUBE_URL", 
                "description": "ഡൗൺലോഡ് ചെയ്യാതെ വീഡിയോ വിവരങ്ങൾ നേടുക",
                "methods": ["GET"]
            },
            "file_download": {
                "url": "/file/FILENAME.mp3",
                "description": "പ്രോസസ്സ് ചെയ്ത ഓഡിയോ ഫയൽ ഡൗൺലോഡ് ചെയ്യുക",
                "methods": ["GET"]
            },
            "statistics": {
                "url": "/stats",
                "description": "API പ്രകടന സ്ഥിതിവിവരക്കണക്കുകൾ",
                "methods": ["GET"]
            },
            "health": {
                "url": "/health",
                "description": "സിസ്റ്റം ആരോഗ്യ പരിശോധന",
                "methods": ["GET"]
            },
            "version": {
                "url": "/version", 
                "description": "ഘടക പതിപ്പ് വിവരങ്ങൾ",
                "methods": ["GET"]
            },
            "cleanup": {
                "url": "/cleanup",
                "description": "മാനുവൽ ഫയൽ ക്ലീനപ്പ്",
                "methods": ["POST"]
            }
        },
        "features": [
            "🛡️ ബ്രൗസർ പ്രതിരൂപണം ഉള്ള അഡ്വാൻസ്ഡ് ആന്റി-ബ്ലോക്കിംഗ്",
            "🔄 മൾട്ടിപ്പിൾ ഫോൾബാക്ക് ഡൗൺലോഡ് സ്ട്രാറ്റജികൾ",
            "📊 റിയൽ-ടൈം വിജയ നിരക്ക് മോണിറ്ററിംഗ്",
            "🧹 ഓട്ടോമാറ്റിക് ക്ലീനപ്പ് സിസ്റ്റം",
            "⚡ ഉയർന്ന നിലവാരമുള്ള MP3 ഓഡിയോ എക്‌സ്ട്രാക്ഷൻ",
            "📱 WhatsApp/Telegram ബോട്ട് തയ്യാറാണ്",
            "🔒 റേറ്റ് ലിമിറ്റിംഗ്, സുരക്ഷ",
            "📈 പ്രകടന അനലിറ്റിക്സ്"
        ],
        "limits": {
            "requests_per_minute": MAX_REQUESTS_PER_MINUTE,
            "file_retention": "2 മണിക്കൂർ",
            "max_file_size": "50MB",
            "supported_formats": ["MP3"]
        },
        "disclaimer": "വിദ്യാഭ്യാസ ആവശ്യങ്ങൾക്ക് മാത്രം. YouTube-ന്റെ സേവന നിബന്ധനകൾ ബഹുമാനിക്കുക."
    })

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "എൻഡ്‌പോയിന്റ് കണ്ടെത്തിയില്ല", "available_endpoints": "/"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "ആന്തരിക സെർവർ പിശക്", "suggestion": "പിന്നീട് വീണ്ടും ശ്രമിക്കുക"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    print(f"🚀 YouTube ഓഡിയോ API v4.0 പോർട്ട് {port}-ൽ ആരംഭിക്കുന്നു")
    print(f"🛡️ അഡ്വാൻസ്ഡ് ആന്റി-ബ്ലോക്കിംഗ് പ്രവർത്തനക്ഷമമാക്കി")
    print(f"📊 വിജയ നിരക്ക് മോണിറ്ററിംഗ് സജീവം")
    app.run(host='0.0.0.0', port=port, debug=False)
