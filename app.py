# app.py - Fixed TTS: lang='hi' (hi-IN not supported in gTTS); Strengthened prompt for pure Devanagari (no English/Latin words); Enhanced logging for WS connects; Cleanup on upload too for disk safety
from flask import Flask, request, jsonify, send_from_directory, render_template_string
from flask_socketio import SocketIO, emit
import os
import google.generativeai as genai
from PIL import Image
from gtts import gTTS
from datetime import datetime
import io
import json
import logging
import shutil  # For cleanup

# Setup logging for detailed logs (visible in Render console)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB limit
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-secret')

# SocketIO: Threading mode for Python 3.13 compatibility; Clients must connect to receive pushes
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', logger=True, engineio_logger=True)

# Configure Gemini - API key from env
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    logger.error("❌ GEMINI_API_KEY not set in environment!")
    raise ValueError("GEMINI_API_KEY required")

genai.configure(api_key=GEMINI_API_KEY)
system_instruction = None
chat = None

# Directories (Render-compatible, relative paths)
SAVE_DIR = './screenshots'
AUDIO_DIR = './static/audio'
os.makedirs(SAVE_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)

# Cleanup old audios on startup (keep last 50 to avoid Render disk limits)
def cleanup_old_audios(max_files=50):
    audio_files = sorted([f for f in os.listdir(AUDIO_DIR) if f.endswith('.mp3')], reverse=True)
    if len(audio_files) > max_files:
        for old_file in audio_files[max_files:]:
            os.remove(os.path.join(AUDIO_DIR, old_file))
        logger.info(f"🧹 Cleaned up {len(audio_files) - max_files} old audio files")

cleanup_old_audios()

# Load system instruction from context.json (once on startup, reset on new game)
def load_system_instruction():
    global system_instruction, chat
    logger.info("🔄 Loading system instruction from context.json...")
    try:
        with open('context.json', 'r', encoding='utf-8') as f:
            context = json.load(f)
        system_instruction = json.dumps(context, ensure_ascii=False, indent=2)
        model = genai.GenerativeModel(
            model_name='gemini-2.5-flash',  # Confirmed available in 2025 (e.g., preview-09-2025)
            system_instruction=system_instruction
        )
        chat = model.start_chat()
        logger.info("✅ System instruction loaded and new chat session started with gemini-2.5-flash.")
    except FileNotFoundError:
        logger.error("❌ context.json not found. Using fallback and creating file.")
        # Fallback context (basic for safety)
        default_context = {
            "title": "Free Fire AI Assistant Context",
            "ai_instructions": {
                "general_rules": [
                    "AI हर 3-4 सेकंड में image observe करेगा लेकिन तभी बोलेगा जब कोई महत्वपूर्ण event दिखे।",
                    "अगर enemy (बंदा) दिखे तो तुरंत कहो: 'बंदा देखा है, उसे मारो!'",
                    "अगर enemy को damage दिया है तो कहो: 'Grenade फेंको!'",
                    "अगर Blue Zone आ रहा हो या shrink हो रहा हो तो कहो: 'Safe Zone में जाओ!'",
                    "अगर teammate down हो जाए तो कहो: 'Teammate को revive करो!'",
                    "अगर player की HP 50 से कम हो तो कहो: 'Medkit लगाओ!'",
                    "अगर 3+ enemies पास में तो कहो: 'छिप जाओ और teammates को बुलाओ!'",
                    "लैंडिंग, लूटिंग या शांत समय में कुछ न बोलो। Response हमेशा छोटा, सटीक और हिंदी में।",
                    "जब कुछ भी महत्वपूर्ण न हो तो कोई response न दो।"
                ]
            }
        }
        with open('context.json', 'w', encoding='utf-8') as f:
            json.dump(default_context, f, ensure_ascii=False, indent=2)
        load_system_instruction()  # Retry load
    except Exception as e:
        logger.error(f"❌ Error loading context: {e}")

# Initialize on startup
load_system_instruction()
SERVER_URL = "https://practice-ppaz.onrender.com"
logger.info(f"🚀 Server initialized at {SERVER_URL}. Ready for screenshots. WS: wss://{SERVER_URL.split('//')[1]}/ws-audio (mobile app must connect as client to receive audio pushes)")

# HTML template for dashboard (updated WS URL)
DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head><title>Free Fire AI Assistant</title></head>
<body>
    <h1>Latest Screenshots (Last 5)</h1>
    <p>Server: https://practice-ppaz.onrender.com</p>
    <p>Connect your client app to wss://practice-ppaz.onrender.com/ws-audio for real-time audio.</p>
    <p>To keep server alive: Ping /ping every 10 min (e.g., via UptimeRobot).</p>
    <p>Total processed: {{ total }}</p>
    {% for file in files %}
        <div>
            <h3>{{ file }}</h3>
            <img src="/image/{{ file }}" alt="{{ file }}" width="300" height="600">
            <p>Time: {{ file.replace('.jpg', '') }}</p>
        </div>
        <hr>
    {% endfor %}
    <p><a href="/">Refresh</a> | <button onclick="fetch('/reset-chat', {method: 'POST'}).then(() => alert('Chat reset for new game!'))">Reset for New Game</button></p>
</body>
</html>
"""

@app.route('/ping', methods=['GET'])
def ping():
    """Keep-alive endpoint - ping this every 10 min to prevent Render sleep."""
    logger.info("🏓 Ping received - server alive!")
    return jsonify({"status": "alive", "server": SERVER_URL}), 200

@app.route('/upload', methods=['POST'])
def upload_screenshot():
    logger.info("📥 POST to /upload received. Headers: %s", dict(request.headers))
    try:
        if 'file' not in request.files:
            logger.warning("⚠️ No file part in request")
            return jsonify({"error": "No file part"}), 400
        
        file = request.files['file']
        logger.info("📄 File received: %s, size: %d bytes", file.filename, file.content_length or 0)
        
        if file.filename == '':
            logger.warning("⚠️ No selected file")
            return jsonify({"error": "No selected file"}), 400
        
        if file and file.filename.lower().endswith('.jpg'):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.jpg"
            filepath = os.path.join(SAVE_DIR, filename)
            file.save(filepath)
            
            size = os.path.getsize(filepath)
            logger.info("💾 Screenshot saved: %s, Size: %d bytes at %s", filename, size, filepath)
            
            # Process with Gemini (only if chat ready)
            audio_url = None
            response_text = None
            try:
                logger.info("🤖 Starting Gemini analysis for %s", filename)
                
                # Load image
                current_image = Image.open(filepath)
                logger.info("🖼️ Image loaded successfully (PIL format)")
                
                # Prepare content (original prompt style) - FIXED: Pure Devanagari, no English/Latin
                prompt_text = "इस नए फ्री फायर स्क्रीनशॉट का विश्लेषण करें: दुश्मन, नीला जोन, कम एचपी, टीममेट डाउन, दुश्मन को नुकसान आदि महत्वपूर्ण घटनाओं के लिए। यदि महत्वपूर्ण हो तो केवल उत्तर दें (संक्षिप्त देवनागरी लिपि में शुद्ध हिंदी सलाह, कोई अंग्रेजी शब्द न हो जैसे 'ग्रेनेड फेंको' की जगह 'ग्रेनेड फेंको' नहीं बल्कि शुद्ध हिंदी); अन्यथा खाली स्ट्रिंग।"
                content_list = [prompt_text, current_image]  # List for content
                logger.info("📝 Prompt prepared: Pure Devanagari enforced")
                
                # Send to chat (persistent until reset)
                if chat:
                    logger.info("💬 Sending to Gemini chat session...")
                    response = chat.send_message(content=content_list)
                    logger.info(f"📨 Gemini full response object: {response}")
                    
                    # Enhanced extraction: Handle empty candidates/parts safely
                    assistant_response = ""
                    if response.candidates and len(response.candidates) > 0:
                        candidate = response.candidates[0]
                        if candidate.content and candidate.content.parts and len(candidate.content.parts) > 0:
                            part = candidate.content.parts[0]
                            if hasattr(part, 'text') and part.text:
                                assistant_response = part.text.strip()
                            logger.info(f"🔍 Candidate details: finish_reason={candidate.finish_reason}, parts={len(candidate.content.parts)}")
                        else:
                            logger.warning("⚠️ No parts in candidate - possible empty response")
                    else:
                        logger.warning("⚠️ No candidates in response - model stopped early (finish_reason likely STOP)")
                    
                    logger.info("📨 Gemini extracted response: '%s'", assistant_response)
                    
                    if assistant_response:
                        response_text = assistant_response
                        logger.info("🔍 Important event detected: '%s'", assistant_response)
                        
                        # Generate TTS audio (fast, Hindi with 'hi' for compatibility - no 'hi-IN')
                        logger.info("🔊 Generating TTS audio...")
                        try:
                            tts = gTTS(text=assistant_response, lang='hi', slow=False)
                            audio_filename = f"audio_{timestamp}.mp3"
                            audio_path = os.path.join(AUDIO_DIR, audio_filename)
                            tts.save(audio_path)
                            
                            # Audio URL (static serve on Render, full URL for client)
                            audio_url = f"{SERVER_URL}/static/audio/{audio_filename}"
                            size_audio = os.path.getsize(audio_path)
                            logger.info("🎵 Audio generated: %s, Size: %d bytes (gTTS lang='hi')", audio_url, size_audio)
                            
                            # Cleanup old audios after save
                            cleanup_old_audios()
                        except Exception as tts_err:
                            logger.error("❌ TTS Generation Error: %s (text was: '%s')", str(tts_err), assistant_response)
                            audio_url = None
                        
                        # Push to connected clients via SocketIO (server-push to WS clients) - Mobile app must be connected to receive
                        if audio_url:
                            socketio.emit('audio_response', {
                                'url': audio_url, 
                                'text': assistant_response,
                                'timestamp': timestamp
                            }, namespace='/ws-audio')
                            logger.info("📡 Audio pushed via WS to all connected clients (threading mode) - Ensure mobile app is connected to wss://practice-ppaz.onrender.com/ws-audio")
                    else:
                        logger.info("🤐 No important event - staying silent (as per rules)")
                else:
                    logger.error("❌ Chat session not initialized")
                    audio_url = None
                    
            except Exception as ai_err:
                logger.error("❌ AI Processing Error: %s", str(ai_err))
                audio_url = None
                response_text = None
            
            logger.info("✅ Upload & process complete for %s. Audio: %s | Response: '%s'", filename, audio_url or "None", response_text or "Empty")
            return jsonify({
                "success": True,
                "filename": filename,
                "size": size,
                "audio_url": audio_url,
                "response_text": response_text,
                "message": "Screenshot processed successfully!"
            }), 200
        else:
            logger.warning("⚠️ Invalid file type: %s (must be JPG)", file.filename)
            return jsonify({"error": "Invalid file type - must be JPG"}), 400
    except Exception as e:
        logger.error("❌ General Upload Error: %s", str(e))
        return jsonify({"error": str(e)}), 500

# Serve images (original)
@app.route('/image/<filename>')
def serve_image(filename):
    filepath = os.path.join(SAVE_DIR, filename)
    if os.path.exists(filepath):
        logger.info("🖼️ Serving image: %s", filename)
        return send_from_directory(SAVE_DIR, filename)
    logger.warning("⚠️ Image not found: %s", filename)
    return "File not found", 404

# Serve audio (static) - Note: /static/audio/<file> serves files
@app.route('/static/audio/<filename>')
def serve_audio(filename):
    filepath = os.path.join(AUDIO_DIR, filename)
    if os.path.exists(filepath):
        logger.info("🎵 Serving audio: %s (exists: yes, path: %s)", filename, filepath)
        return send_from_directory(AUDIO_DIR, filename)
    logger.warning("⚠️ Audio not found: %s (path: %s - check if generated)", filename, filepath)
    return "File not found", 404

# Reset chat for new game (reloads context, new session)
@app.route('/reset-chat', methods=['POST'])
def reset_chat():
    logger.info("🔄 Reset chat requested - starting new session for game")
    try:
        load_system_instruction()  # Reloads and starts fresh chat
        cleanup_old_audios()  # Clean on reset too
        logger.info("✅ Chat reset successful")
        return jsonify({"success": True, "message": "Chat reset for new game."}), 200
    except Exception as e:
        logger.error("❌ Reset error: %s", str(e))
        return jsonify({"error": str(e)}), 500

# Dashboard (original, with latest 5)
@app.route('/', methods=['GET'])
def dashboard():
    logger.info("📊 Dashboard accessed")
    all_files = [f for f in os.listdir(SAVE_DIR) if f.endswith('.jpg')]
    files = sorted(all_files, reverse=True)[:5]
    total = len(all_files)  # Fixed: only count JPGs
    logger.info("📋 Dashboard showing %d files, total: %d", len(files), total)
    return render_template_string(DASHBOARD_TEMPLATE, files=files, total=total)

# SocketIO events (for WS-audio namespace) - Mobile app connects here to receive
@socketio.on('connect', namespace='/ws-audio')
def handle_connect():
    logger.info("🔌 Client connected to /ws-audio: %s (now %d connected - audio pushes will reach)", request.sid, len(socketio.server.manager.rooms.get('/ws-audio', [])))
    emit('connected', {'data': 'Connected to AI audio stream at https://practice-ppaz.onrender.com - Ready for pushes!'})

@socketio.on('disconnect', namespace='/ws-audio')
def handle_disconnect():
    logger.info("🔌 Client disconnected from /ws-audio: %s (now %d connected)", request.sid, len(socketio.server.manager.rooms.get('/ws-audio', [])) - 1)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🚀 Starting server on port {port} (Render free tier compatible, threading mode)")
    socketio.run(app, host='0.0.0.0', port=port, debug=False)  # debug=False for prod
