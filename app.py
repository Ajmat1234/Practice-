from flask import Flask, request, jsonify, send_from_directory, render_template_string
import os
import google.generativeai as genai
from PIL import Image
from gtts import gTTS
from datetime import datetime
import json
import logging
from collections import deque
import threading

# Setup logging (more verbose for polling)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1000 * 1024  # 10MB limit
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-secret')

# Globals for latest audio (polling support)
latest_audio_url = None
latest_timestamp = None
latest_response_text = None  # Optional: Store text for logging

# Image queue for buffering (max 5 to skip overload)
image_queue = deque(maxlen=5)
queue_lock = threading.Lock()
models_ready = False
ready_model_count = 0

# Configure Gemini with multiple keys
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GEMINI_API_KEY_2 = os.environ.get('GEMINI_API_KEY_2', GEMINI_API_KEY)  # Fallback to first if not set

if not GEMINI_API_KEY:
    logger.error("❌ GEMINI_API_KEY not set!")
    raise ValueError("GEMINI_API_KEY required")

# Models: 3 valid ones
model_names = ['gemini-2.5-flash-lite', 'learnlm-2.0-flash-experimental', 'gemini-2.5-flash-lite']
api_keys = [GEMINI_API_KEY, GEMINI_API_KEY, GEMINI_API_KEY_2]

chats = []
system_instruction = None

# Directories
SAVE_DIR = './screenshots'
AUDIO_DIR = './static/audio'
os.makedirs(SAVE_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)

# Cleanup old audios
def cleanup_old_audios(max_files=50):
    audio_files = sorted([f for f in os.listdir(AUDIO_DIR) if f.endswith('.mp3')], reverse=True)
    if len(audio_files) > max_files:
        for old_file in audio_files[max_files:]:
            os.remove(os.path.join(AUDIO_DIR, old_file))
        logger.info(f"🧹 Cleaned up {len(audio_files) - max_files} old audio files")

cleanup_old_audios()

# Warmup function for models (sequential for stability)
def warmup_model(chat, model_name):
    try:
        # Dummy prompt for warmup (no image, simple text)
        dummy_prompt = "फ्री फायर गेम में एक महत्वपूर्ण घटना का वर्णन करें।"
        response = chat.send_message(dummy_prompt)
        if response.candidates:
            logger.info(f"✅ Warmup complete for {model_name}")
            return True
    except Exception as e:
        logger.error(f"❌ Warmup failed for {model_name}: {e}")
    return False

# Load system instruction and warmup all models
def load_system_instruction():
    global system_instruction, chats, models_ready, ready_model_count
    logger.info("🔄 Loading system instruction from context.json to all models...")
    try:
        with open('context.json', 'r', encoding='utf-8') as f:
            context = json.load(f)
        system_instruction = json.dumps(context, ensure_ascii=False, indent=2)
        
        chats = []
        initialized_count = 0
        for i, (model_name, api_key) in enumerate(zip(model_names, api_keys)):
            # Temp configure for each
            genai.configure(api_key=api_key)
            try:
                model = genai.GenerativeModel(model_name=model_name, system_instruction=system_instruction)
                chat = model.start_chat()
                chats.append((chat, model_name, api_key))
                initialized_count += 1
                logger.info(f"✅ Model {i+1} ({model_name}) initialized with key {1 if i < 2 else 2}")
            except Exception as model_err:
                logger.error(f"❌ Failed to init model {model_name}: {model_err}")
                chats.append(None)
        
        # Sequential warmup (stable, no parallel issues)
        logger.info("🔥 Starting sequential model warmup...")
        warmup_success = 0
        for chat_tuple in chats:
            if chat_tuple:
                chat, model_name, _ = chat_tuple
                if warmup_model(chat, model_name):  # Individual call with internal timeout
                    warmup_success += 1
        
        ready_model_count = warmup_success
        models_ready = ready_model_count >= 1  # Proceed if at least 1 ready
        logger.info(f"✅ Warmup done: {warmup_success}/{initialized_count} models ready. Proceeding...")
    except FileNotFoundError:
        logger.error("❌ context.json not found. Using fallback.")
        # Fallback context with specified rules
        default_context = {
            "title": "Free Fire AI Assistant Context",
            "ai_instructions": {
                "general_rules": [
                    "हर सेकंड image observe करो लेकिन तभी बोलोगे जब कोई महत्वपूर्ण event दिखे।",
                    "अगर enemy (बंदा) दिखे तो तुरंत कहो: 'बंदा देखा है, उसे मारो! या अगल बगल देखो'",
                    "अगर enemy को damage दिया है तो कहो: 'ग्रेनेड फेंको! या बन्दे देख कर रस करो '",
                    "अगर Blue Zone आ रहा हो या shrink हो रहा हो तो कहो: 'सेफ जोन में जाओ!'",
                    "अगर teammate down हो जाए तो कहो: 'दोस्तों को मदद करो!'",
                    "अगर player की HP 50 से कम हो तो कहो: 'ग्लू लगाकर मेडिसन लगाओ! या दौड़ते हुए हेल्थ बढ़ाओ '",
                    "अगर 3+ enemies पास में तो कहो: 'छिप जाओ और दोस्तों को बुलाओ!'",
                    "लैंडिंग, लूटिंग या शांत समय में कुछ न बोलो। Response हमेशा छोटा, सटीक और देवनागरी हिंदी में।",
                    "जब कुछ भी महत्वपूर्ण न हो तो कोई response न दो।"
                ]
            }
        }
        with open('context.json', 'w', encoding='utf-8') as f:
            json.dump(default_context, f, ensure_ascii=False, indent=2)
        load_system_instruction()
    except Exception as e:
        logger.error(f"❌ Error loading context: {e}")
        models_ready = False

load_system_instruction()
SERVER_URL = "https://practice-ppaz.onrender.com"
logger.info(f"🚀 Server initialized at {SERVER_URL}. Models ready: {models_ready} ({ready_model_count}/3). Polling: {SERVER_URL}/latest-audio")

DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head><title>Free Fire AI Assistant</title></head>
<body>
    <h1>Latest Screenshots (Last 5)</h1>
    <p>Server: https://practice-ppaz.onrender.com</p>
    <p>Connect your client app to https://practice-ppaz.onrender.com for polling /latest-audio every 1-2s.</p>
    <p>To keep server alive: Ping /ping every 10 min (e.g., via UptimeRobot).</p>
    <p>Models Ready: {{ ready }} ({{ count }}/3)</p>
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

def analyze_with_model(chat_tuple, content_list, timeout=5):
    """Analyze image with a single model and return response or None if invalid."""
    if not chat_tuple:
        return None, "Skipped"
    chat, model_name, _ = chat_tuple
    try:
        response = chat.send_message(content=content_list)
        assistant_response = ""
        if response.candidates and len(response.candidates) > 0:
            candidate = response.candidates[0]
            if candidate.content and candidate.content.parts and len(candidate.content.parts) > 0:
                part = candidate.content.parts[0]
                if hasattr(part, 'text') and part.text:
                    assistant_response = part.text.strip()
        # Check if valid: more than 4 words
        word_count = len(assistant_response.split())
        if word_count > 4:
            return assistant_response, model_name
        else:
            logger.debug(f"⚠️ Response from {model_name} too short ({word_count} words): '{assistant_response}'")
            return None, model_name
    except Exception as e:
        logger.error(f"❌ Error in model {model_name}: {e}")
        return None, model_name

@app.route('/ping', methods=['GET'])
def ping():
    logger.info("🏓 Ping received - server alive!")
    return jsonify({"status": "alive", "server": SERVER_URL, "models_ready": models_ready, "ready_count": ready_model_count}), 200

@app.route('/upload', methods=['POST'])
def upload_screenshot():
    global latest_audio_url, latest_timestamp, latest_response_text, models_ready
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
            
            # Queue the image if models not ready or queue full
            with queue_lock:
                if not models_ready or len(image_queue) >= 5:
                    if not models_ready:
                        logger.info("⏳ Models warming up - skipping image %s", filename)
                    else:
                        logger.info("🗑️ Queue full (5) - skipping oldest image")
                    # Still save but skip process
                    return jsonify({
                        "success": True,
                        "filename": filename,
                        "size": size,
                        "skipped": True,
                        "message": "Image queued/skipped for speed. Poll /latest-audio."
                    }), 200
                image_queue.append((filepath, timestamp, filename))
            
            # Process from queue (only if ready)
            if models_ready:
                audio_url = None
                response_text = None
                try:
                    logger.info("🤖 Starting Gemini analysis for %s with %d models", filename, ready_model_count)
                    
                    current_image = Image.open(filepath)
                    logger.info("🖼️ Image loaded successfully (PIL format)")
                    
                    prompt_text = "इस नए फ्री फायर स्क्रीनशॉट का विश्लेषण करें: दुश्मन, नीला जोन, कम एचपी, टीममेट डाउन, दुश्मन को नुकसान आदि महत्वपूर्ण घटनाओं के लिए। यदि महत्वपूर्ण हो तो केवल उत्तर दें (संक्षिप्त देवनागरी लिपि में शुद्ध हिंदी सलाह, कोई अंग्रेजी शब्द न हो); अन्यथा खाली स्ट्रिंग। यदि कोई महत्वपूर्ण घटना न हो तो बिल्कुल खाली string लौटाओ, कोई punctuation या space न डालो।"
                    content_list = [prompt_text, current_image]
                    logger.info("📝 Prompt prepared: Pure Devanagari enforced, shortened")
                    
                    # Select ready models (up to 3)
                    selected_chats = [(chat, name, key) for chat, name, key in chats if chat is not None]
                    if len(selected_chats) < 1:
                        raise ValueError("No ready models available")
                    
                    # Sequential analysis for stability (first ready model)
                    for chat_tuple in selected_chats[:1]:  # Use first ready for speed, no parallel
                        result, model_name = analyze_with_model(chat_tuple, content_list)
                        if result:
                            response_text = result
                            logger.info("🔍 Valid event from %s: '%s'", model_name, result)
                            
                            # Generate TTS
                            logger.info("🔊 Generating TTS audio...")
                            tts = gTTS(text=response_text, lang='hi', slow=False)
                            audio_filename = f"audio_{timestamp}.mp3"
                            audio_path = os.path.join(AUDIO_DIR, audio_filename)
                            tts.save(audio_path)
                            
                            audio_url = f"{SERVER_URL}/static/audio/{audio_filename}"
                            size_audio = os.path.getsize(audio_path)
                            logger.info("🎵 Audio generated: %s, Size: %d bytes (gTTS lang='hi', slow=False)", audio_url, size_audio)
                            
                            # Update global latest
                            latest_audio_url = audio_url
                            latest_timestamp = datetime.now().isoformat()
                            latest_response_text = response_text
                            break
                    
                    if not response_text:
                        logger.info("🤐 No valid event from models - staying silent, no audio")
                        # Reset latest if no event
                        latest_audio_url = None
                        latest_timestamp = None
                        latest_response_text = None
                            
                    cleanup_old_audios()
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
                    "message": "Screenshot processed successfully! Poll /latest-audio for new audio."
                }), 200
            else:
                return jsonify({
                    "success": True,
                    "filename": filename,
                    "size": size,
                    "queued": True,
                    "message": "Image queued during warmup. Poll /latest-audio."
                }), 200
        else:
            logger.warning("⚠️ Invalid file type: %s (must be JPG)", file.filename)
            return jsonify({"error": "Invalid file type - must be JPG"}), 400
    except Exception as e:
        logger.error("❌ General Upload Error: %s", str(e))
        return jsonify({"error": str(e)}), 500

# Polling endpoint for latest audio
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
    global latest_audio_url, latest_timestamp, latest_response_text, models_ready
    logger.info("🔄 Reset chat requested")
    try:
        load_system_instruction()
        cleanup_old_audios()
        # Reset latest audio on reset
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
    global models_ready, ready_model_count
    logger.info("📊 Dashboard accessed")
    all_files = [f for f in os.listdir(SAVE_DIR) if f.endswith('.jpg')]
    files = sorted(all_files, reverse=True)[:5]
    total = len(all_files)
    logger.info("📋 Dashboard showing %d files, total: %d", len(files), total)
    return render_template_string(DASHBOARD_TEMPLATE, files=files, total=total, ready=str(models_ready), count=ready_model_count)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🚀 Starting server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
