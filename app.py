# app.py
from flask import Flask, request, jsonify, send_from_directory, render_template_string
from flask_socketio import SocketIO, emit
import os
import google.generativeai as genai
from PIL import Image
from gtts import gTTS
from datetime import datetime
import io
import json

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB limit
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-secret')

# SocketIO for real-time audio notifications
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Configure Gemini
genai.configure(api_key=os.environ.get('GEMINI_API_KEY'))
system_instruction = None
chat = None

# Directories
SAVE_DIR = './screenshots'
AUDIO_DIR = './static/audio'
os.makedirs(SAVE_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)

# Load system instruction from context.json
def load_system_instruction():
    global system_instruction, chat
    try:
        with open('context.json', 'r', encoding='utf-8') as f:
            context = json.load(f)
        system_instruction = json.dumps(context, ensure_ascii=False, indent=2)
        model = genai.GenerativeModel(
            model_name='gemini-1.5-flash',
            system_instruction=system_instruction
        )
        chat = model.start_chat()
        print("✅ System instruction loaded and chat initialized.")
    except FileNotFoundError:
        print("❌ context.json not found. Creating a default one.")
        # Fallback: Create basic file
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
                    "जब कुछ महत्वपूर्ण न हो तो कोई response न दो।"
                ]
            }
        }
        with open('context.json', 'w', encoding='utf-8') as f:
            json.dump(default_context, f, ensure_ascii=False, indent=2)
        load_system_instruction()  # Retry

# Initialize on startup
load_system_instruction()

# HTML template for dashboard (optional, to view images)
DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head><title>Free Fire AI Assistant</title></head>
<body>
    <h1>Latest Screenshots (Last 5)</h1>
    <p>Connect your client to /ws-audio for real-time audio responses.</p>
    {% for file in files %}
        <div>
            <h3>{{ file }}</h3>
            <img src="/image/{{ file }}" alt="{{ file }}" width="300" height="600">
            <p>Time: {{ file.replace('.jpg', '') }}</p>
        </div>
        <hr>
    {% endfor %}
    <p><a href="/">Refresh</a> | <a href="/reset-chat">Reset Chat (New Game)</a></p>
</body>
</html>
"""

@app.route('/upload', methods=['POST'])
def upload_screenshot():
    print("POST to /upload received")
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file part"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400
        
        if file and file.filename.lower().endswith('.jpg'):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.jpg"
            filepath = os.path.join(SAVE_DIR, filename)
            file.save(filepath)
            
            size = os.path.getsize(filepath)
            print(f"✅ Screenshot saved: {filename}, Size: {size} bytes")
            
            # Process with Gemini
            audio_url = None
            try:
                # Load image
                current_image = Image.open(filepath)
                
                # Prepare content
                prompt_text = "Analyze this Free Fire screenshot for critical events like enemies, blue zone, HP, teammate down, etc. Respond only if something important; else empty string."
                contents = [prompt_text, current_image]
                
                # Send to chat
                if chat:
                    response = chat.send_message(contents=contents)
                    assistant_response = response.text.strip()
                    
                    if assistant_response:
                        print(f"🤖 Gemini Response: {assistant_response}")
                        
                        # Generate TTS audio
                        tts = gTTS(text=assistant_response, lang='hi', slow=False)
                        audio_filename = f"audio_{timestamp}.mp3"
                        audio_path = os.path.join(AUDIO_DIR, audio_filename)
                        tts.save(audio_path)
                        
                        # Audio URL (Render serves static/)
                        audio_url = f"/static/audio/{audio_filename}"
                        print(f"🔊 Audio generated: {audio_url}")
                        
                        # Emit via SocketIO to connected clients
                        socketio.emit('audio_response', {'url': audio_url, 'text': assistant_response})
                    else:
                        print("🤖 No important event - silent.")
                else:
                    print("❌ Chat not initialized.")
                    
            except Exception as ai_err:
                print(f"❌ AI Processing Error: {ai_err}")
                audio_url = None
            
            return jsonify({
                "success": True,
                "filename": filename,
                "size": size,
                "audio_url": audio_url,
                "message": "Processed successfully!"
            }), 200
        else:
            return jsonify({"error": "Invalid file type - must be JPG"}), 400
    except Exception as e:
        print(f"❌ Upload Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/image/<filename>')
def serve_image(filename):
    filepath = os.path.join(SAVE_DIR, filename)
    if os.path.exists(filepath):
        return send_from_directory(SAVE_DIR, filename)
    return "File not found", 404

@app.route('/reset-chat', methods=['POST'])
def reset_chat():
    global chat
    load_system_instruction()  # Reloads and starts new chat
    return jsonify({"success": True, "message": "Chat reset for new game."}), 200

@app.route('/', methods=['GET'])
def dashboard():
    files = [f for f in os.listdir(SAVE_DIR) if f.endswith('.jpg')]
    files.sort(reverse=True)
    files = files[:5]
    return render_template_string(DASHBOARD_TEMPLATE, files=files)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
