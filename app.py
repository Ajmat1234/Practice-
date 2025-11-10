from flask import Flask, request, jsonify, send_from_directory, render_template_string
import os
import google.generativeai as genai
from PIL import Image
from gtts import gTTS
from datetime import datetime
import io
import json
import logging
import shutil  # For cleanup
import asyncio  # For async WS (kept but unused now)
from flask_sock import Sock  # For plain WebSocket support in Flask (commented out)
from pydub import AudioSegment  # For speeding up audio

# Setup logging (more verbose for polling)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1000 * 1024  # 10MB limit
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-secret')

# Flask-Sock for plain WebSockets (commented out - polling now)
# sock = Sock(app)

# NEW: Globals for latest audio (polling support)
latest_audio_url = None
latest_timestamp = None
latest_response_text = None  # Optional: Store text for logging

# NEW: Globals for model rotation
current_phase = 1
phase_counts = {1: 0, 2: 0, 3: 0}
phase_quotas = {1: 30, 2: 15, 3: 15}

# Configure Gemini
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    logger.error("❌ GEMINI_API_KEY not set!")
    raise ValueError("GEMINI_API_KEY required")

genai.configure(api_key=GEMINI_API_KEY)
system_instruction = None
chat1 = None  # gemini-2.0-flash-lite
chat2 = None  # gemini-2.0-flash
chat3 = None  # gemini-2.5-flash-lite

# Directories
SAVE_DIR = './screenshots'
AUDIO_DIR = './static/audio'
os.makedirs(SAVE_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)

# Track connected WS clients (commented out - unused now)
# clients = set()

# Cleanup old audios
def cleanup_old_audios(max_files=50):
    audio_files = sorted([f for f in os.listdir(AUDIO_DIR) if f.endswith('.mp3')], reverse=True)
    if len(audio_files) > max_files:
        for old_file in audio_files[max_files:]:
            os.remove(os.path.join(AUDIO_DIR, old_file))
        logger.info(f"🧹 Cleaned up {len(audio_files) - max_files} old audio files")

cleanup_old_audios()

# Load system instruction to all three models
def load_system_instruction():
    global system_instruction, chat1, chat2, chat3, current_phase, phase_counts
    logger.info("🔄 Loading system instruction from context.json to all models...")
    try:
        with open('context.json', 'r', encoding='utf-8') as f:
            context = json.load(f)
        system_instruction = json.dumps(context, ensure_ascii=False, indent=2)
        
        # Model 1: gemini-2.0-flash-lite (30 RPM)
        model1 = genai.GenerativeModel(
            model_name='gemini-2.0-flash-lite',
            system_instruction=system_instruction
        )
        chat1 = model1.start_chat()
        
        # Model 2: gemini-2.0-flash (15 RPM)
        model2 = genai.GenerativeModel(
            model_name='gemini-2.0-flash',
            system_instruction=system_instruction
        )
        chat2 = model2.start_chat()
        
        # Model 3: gemini-2.5-flash-lite (15 RPM)
        model3 = genai.GenerativeModel(
            model_name='gemini-2.5-flash-lite',
            system_instruction=system_instruction
        )
        chat3 = model3.start_chat()
        
        # Reset phases for new session
        current_phase = 1
        phase_counts = {1: 0, 2: 0, 3: 0}
        
        logger.info("✅ System instruction loaded to all three models and new chat sessions started.")
    except FileNotFoundError:
        logger.error("❌ context.json not found. Using fallback.")
        # Fallback context (same as your code)
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
        load_system_instruction()
    except Exception as e:
        logger.error(f"❌ Error loading context: {e}")

load_system_instruction()
SERVER_URL = "https://practice-ppaz.onrender.com"
logger.info(f"🚀 Server initialized at {SERVER_URL}. Ready for screenshots. Polling: {SERVER_URL}/latest-audio")

DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head><title>Free Fire AI Assistant</title></head>
<body>
    <h1>Latest Screenshots (Last 5)</h1>
    <p>Server: https://practice-ppaz.onrender.com</p>
    <p>Connect your client app to https://practice-ppaz.onrender.com for polling /latest-audio every 3s.</p>
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
    logger.info("🏓 Ping received - server alive!")
    return jsonify({"status": "alive", "server": SERVER_URL}), 200

@app.route('/upload', methods=['POST'])
def upload_screenshot():
    global current_phase, phase_counts, latest_audio_url, latest_timestamp, latest_response_text
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
            
            # Process with Gemini (rotated model)
            audio_url = None
            response_text = None
            try:
                logger.info("🤖 Starting Gemini analysis for %s (Phase: %d, Count: %d/%d)", filename, current_phase, phase_counts[current_phase], phase_quotas[current_phase])
                
                current_image = Image.open(filepath)
                logger.info("🖼️ Image loaded successfully (PIL format)")
                
                prompt_text = "इस नए फ्री फायर स्क्रीनशॉट का विश्लेषण करें: दुश्मन, नीला जोन, कम एचपी, टीममेट डाउन, दुश्मन को नुकसान आदि महत्वपूर्ण घटनाओं के लिए। यदि महत्वपूर्ण हो तो केवल उत्तर दें (संक्षिप्त देवनागरी लिपि में शुद्ध हिंदी सलाह, कोई अंग्रेजी शब्द न हो); अन्यथा खाली स्ट्रिंग।"
                content_list = [prompt_text, current_image]
                logger.info("📝 Prompt prepared: Pure Devanagari enforced")
                
                # Select chat based on current phase
                if current_phase == 1 and chat1:
                    response = chat1.send_message(content=content_list)
                    phase_counts[1] += 1
                    model_name = "gemini-2.0-flash-lite"
                elif current_phase == 2 and chat2:
                    response = chat2.send_message(content=content_list)
                    phase_counts[2] += 1
                    model_name = "gemini-2.0-flash"
                elif current_phase == 3 and chat3:
                    response = chat3.send_message(content=content_list)
                    phase_counts[3] += 1
                    model_name = "gemini-2.5-flash-lite"
                else:
                    logger.error("❌ No valid chat for current phase")
                    return jsonify({"error": "Model not available"}), 500
                
                # Switch phase if quota reached
                if phase_counts[current_phase] >= phase_quotas[current_phase]:
                    if current_phase == 3:
                        current_phase = 1
                        phase_counts = {1: 0, 2: 0, 3: 0}
                        logger.info("🔄 Full cycle complete - Reset to phase 1")
                    else:
                        current_phase += 1
                        logger.info("🔄 Switched to phase %d", current_phase)
                
                assistant_response = ""
                if response.candidates and len(response.candidates) > 0:
                    candidate = response.candidates[0]
                    if candidate.content and candidate.content.parts and len(candidate.content.parts) > 0:  # Safe check
                        part = candidate.content.parts[0]
                        if hasattr(part, 'text') and part.text:
                            assistant_response = part.text.strip()
                    else:
                        logger.warning("⚠️ Gemini response parts empty - no text extracted")
                logger.info("📨 Gemini extracted response from %s: '%s'", model_name, assistant_response)
                
                # Skip if empty response
                if assistant_response:
                    response_text = assistant_response
                    logger.info("🔍 Important event detected: '%s'", assistant_response)
                    
                    # Generate TTS (gTTS 'hi' lang) and speed up
                    logger.info("🔊 Generating TTS audio...")
                    tts = gTTS(text=assistant_response, lang='hi', slow=False)
                    audio_filename = f"audio_{timestamp}.mp3"
                    audio_path = os.path.join(AUDIO_DIR, audio_filename)
                    tts.save(audio_path)
                    
                    # Speed up audio with pydub
                    audio = AudioSegment.from_mp3(audio_path)
                    faster_audio = audio.speedup(playback_speed=1.2)
                    faster_audio.export(audio_path, format="mp3")
                    
                    audio_url = f"{SERVER_URL}/static/audio/{audio_filename}"
                    size_audio = os.path.getsize(audio_path)
                    logger.info("🎵 Audio generated and sped up: %s, Size: %d bytes (gTTS lang='hi', 1.2x speed)", audio_url, size_audio)
                    
                    # NEW: Update global latest for polling
                    latest_audio_url = audio_url
                    latest_timestamp = datetime.now().isoformat()
                    latest_response_text = assistant_response
                else:
                    logger.info("🤐 No important event (empty response) - staying silent, no audio")
                    # Reset latest if no event
                    latest_audio_url = None
                    latest_timestamp = None
                    latest_response_text = None
                        
                cleanup_old_audios()
            except Exception as ai_err:
                logger.error("❌ AI Processing Error: %s", str(ai_err))
                audio_url = None
                response_text = None
            
            logger.info("✅ Upload & process complete for %s. Audio: %s | Response: '%s' | Phase: %d", filename, audio_url or "None", response_text or "Empty", current_phase)
            return jsonify({
                "success": True,
                "filename": filename,
                "size": size,
                "audio_url": audio_url,
                "response_text": response_text,
                "message": "Screenshot processed successfully! Poll /latest-audio for new audio."
            }), 200
        else:
            logger.warning("⚠️ Invalid file type: %s (must be JPG)", file.filename)
            return jsonify({"error": "Invalid file type - must be JPG"}), 400
    except Exception as e:
        logger.error("❌ General Upload Error: %s", str(e))
        return jsonify({"error": str(e)}), 500

# NEW: Polling endpoint for latest audio
@app.route('/latest-audio', methods=['GET'])
def get_latest_audio():
    global latest_audio_url, latest_timestamp, latest_response_text
    if latest_audio_url and latest_timestamp:
        logger.info("📡 Polling request - returning latest: %s", latest_audio_url)
        return jsonify({
            "audio_url": latest_audio_url,
            "timestamp": latest_timestamp,
            "response_text": latest_response_text  # Optional: for UI hint
        }), 200
    else:
        logger.debug("📡 Polling - no new audio")
        return jsonify({"audio_url": None, "timestamp": None, "response_text": None}), 200

# OLD: Async WS send (commented out)
# async def send_audio_to_clients(audio_url, text):
#     global clients
#     if not clients:
#         logger.warning("⚠️ No WS clients connected - skipping push")
#         return
#     message = json.dumps({'audio_url': audio_url, 'text': text})
#     disconnected = set()
#     sent_count = 0
#     for client in clients.copy():  # Copy to avoid modification during iteration
#         try:
#             await client.send(message)
#             sent_count += 1
#             logger.info(f"📤 Sent audio to client ({sent_count}/{len(clients)}): {audio_url}")
#         except Exception as e:
#             logger.error(f"❌ Failed to send to client: {e}")
#             disconnected.add(client)
#     clients -= disconnected  # Remove dead clients
#     logger.info(f"📤 Push complete: Sent to {sent_count} clients, removed {len(disconnected)} dead")

# OLD: WS route (commented out)
# @sock.route('/ws-audio')
# async def ws_audio(ws):
#     client_id = id(ws)  # Unique ID for logging
#     logger.info("🔌 WS Client CONNECTED to /ws-audio (ID: %d) - Total clients now: %d", client_id, len(clients) + 1)
#     clients.add(ws)
#     logger.info("🔌 Client %d added to set - Current clients: %d", client_id, len(clients))
#     try:
#         async for message in ws:
#             logger.info(f"📨 WS message received from client %d: %s", client_id, message)
#     except Exception as e:
#         logger.error(f"❌ WS error for client %d: %s", client_id, e)
#     finally:
#         clients.discard(ws)
#         logger.info("🔌 WS Client %d DISCONNECTED - Total clients now: %d", client_id, len(clients))

# Other routes (same)
@app.route('/image/<filename>')
def serve_image(filename):
    filepath = os.path.join(SAVE_DIR, filename)
    if os.path.exists(filepath):
        logger.info("🖼️ Serving image: %s", filename)
        return send_from_directory(SAVE_DIR, filename)
    logger.warning("⚠️ Image not found: %s", filename)
    return "File not found", 404

@app.route('/static/audio/<filename>')
def serve_audio(filename):
    filepath = os.path.join(AUDIO_DIR, filename)
    if os.path.exists(filepath):
        logger.info("🎵 Serving audio: %s", filename)
        return send_from_directory(AUDIO_DIR, filename)
    logger.warning("⚠️ Audio not found: %s", filename)
    return "File not found", 404

@app.route('/reset-chat', methods=['POST'])
def reset_chat():
    global current_phase, phase_counts, latest_audio_url, latest_timestamp, latest_response_text
    logger.info("🔄 Reset chat requested")
    try:
        load_system_instruction()
        cleanup_old_audios()
        # NEW: Reset latest audio on reset
        latest_audio_url = None
        latest_timestamp = None
        latest_response_text = None
        logger.info("✅ Chat reset successful")
        return jsonify({"success": True, "message": "Chat reset for new game."}), 200
    except Exception as e:
        logger.error("❌ Reset error: %s", str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/', methods=['GET'])
def dashboard():
    logger.info("📊 Dashboard accessed")
    all_files = [f for f in os.listdir(SAVE_DIR) if f.endswith('.jpg')]
    files = sorted(all_files, reverse=True)[:5]
    total = len(all_files)
    logger.info("📋 Dashboard showing %d files, total: %d", len(files), total)
    return render_template_string(DASHBOARD_TEMPLATE, files=files, total=total)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🚀 Starting server on port {port}")
    # sock.run(app, host='0.0.0.0', port=port, debug=False)  # Commented: Use app.run for polling-only
    app.run(host='0.0.0.0', port=port, debug=False)
