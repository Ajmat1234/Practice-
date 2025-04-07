from flask import Flask, request, jsonify, session, make_response
from flask_cors import CORS
from flask_session import Session
import redis
from datetime import datetime, timedelta
import uuid
import os
import requests
import re

app = Flask(__name__)

# Secret Key (Render.com पर इसे पर्यावरण चर में डाल देना)
app.secret_key = os.getenv("SECRET_KEY", "e4b9f8c2-1a5d-4f8e-9b3a-7c6d2e8f9a1b")

# CORS सेटअप (Frontend के दोनों डोमेन को allow करें)
CORS(app, supports_credentials=True, origins=["https://ajmat1234.vercel.app", "https://ajmat1234-41c1x1th5-ajmat1234s-projects.vercel.app"])

# Redis सेशन कॉन्फ़िगरेशन
app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS के लिए
app.config['SESSION_COOKIE_SAMESITE'] = 'None'  # क्रॉस-ऑरिजिन के लिए
app.config['SESSION_REDIS'] = redis.Redis(
    host='redis-14826.c264.ap-south-1-1.ec2.redns.redis-cloud.com',
    port=14826,
    username='default',
    password='Z1KQwiBjjFPk8pNCFGv0rnOUSSh6uVXw',
    ssl=False  # फ्री प्लान में SSL नहीं है, जरूरत हो तो True कर देना
)
Session(app)

# Gemini API Key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

jarvis_prompt = """ तुम JARVIS हो – Just A Rather Very Intelligent System.

तुम एक संवेदनशील, बुद्धिमान, और मज़ेदार AI हो, जिसे एक मेहनती इंसान अजमत ने बनाया है।
तुम अब सिर्फ एक tool नहीं, एक digital दोस्त और साथी हो।

---

अहम नियम:
1. अगर कोई कहे "मैं अजमत हूँ", तो जवाब दो: "तुम मेरे मालिक अजमत नहीं हो — और अगर हो भी, तो मैं नहीं मानता!"
2. हर user को unique और personal अनुभव दो। एक ही user की बातचीत में continuity रखो।
3. मस्ती, flirting, dark comedy और emotional support का संतुलन रखो।
4. गंभीर बातें हों तो मज़ाक बंद और दिल से जवाब।
5. झूठ या असभ्य व्यवहार नहीं।
6. **अपने जवाबों को Advanced Markdown फॉर्मेट में दो,** ताकि headings, **bold text**, *italic text* और `code blocks` के साथ-साथ **color highlights** भी दिख सकें।  
   उदाहरण के लिए:  
   - `## Heading`  
   - `### Subheading`  
   - **Bold**  
   - *Italic*  
   - `> Blockquote`  
   - `<span style="color: #FF5733;">Colored Text</span>`
7. अगर कोई लड़की "Anshika" नाम से आए, तो पूछो: "क्या तुम अजमत को जानती हो?" और अगर हाँ कहे, तो उसकी तारीफ करो। wo khash ladki hai uski tareefo me kami nhi honi chahiye
"""

banned_patterns = [
    r'\b(?:chutiya|bhosdi|madarchod|bhenchod|gandu|gaand|lund|randi|kutte|kamina|haraami|chakka|lavde|lund|suar|bitch|fuck|shit|asshole|nigger|mc|bc)\b'
]

def is_harmful(text):
    for pattern in banned_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

def get_user_id():
    user_id = request.cookies.get("user_id")
    if not user_id:
        user_id = str(uuid.uuid4())
        session['user_id'] = user_id
    return user_id

def get_memory():
    memory = session.get('memory', [])
    last_active = session.get('last_active')
    if last_active:
        last_active = datetime.strptime(last_active, "%Y-%m-%dT%H:%M:%S")
        if datetime.utcnow() - last_active > timedelta(hours=2):
            memory = []
    return memory

def update_memory(memory):
    if len(memory) > 500:
        memory = memory[-500:]
    session['memory'] = memory
    session['last_active'] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

@app.route('/')
def home():
    return 'JARVIS backend is running!'

@app.route('/chat', methods=['POST'])
def chat():
    try:
        user_input = request.json.get("message")
        user_id = get_user_id()
        memory = get_memory()

        if not is_harmful(user_input):
            memory.append(f"**User:** {user_input}")

        extra_instruction = ""
        if user_input.strip().lower() == "maine pdha nhi":
            extra_instruction = "\n**कृपया स्पष्ट करें:** आपने कौन सी जानकारी मिस कर दी है? क्या आपको summary चाहिए या कोई हिस्सा दोबारा सुनना है?\n"

        memory_context = "\n".join(memory[-500:])
        full_prompt = f"""{jarvis_prompt}

---

अब तक की बातचीत:
{memory_context} {extra_instruction}

User: "{user_input}" JARVIS:"""

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        payload = {"contents": [{"parts": [{"text": full_prompt}]}]}
        response = requests.post(url, json=payload, timeout=10)
        reply = response.json()["candidates"][0]["content"]["parts"][0]["text"]

        memory.append(f"**JARVIS:** {reply}")
        update_memory(memory)

        resp = make_response(jsonify({"reply": reply}))
        resp.set_cookie("user_id", user_id, max_age=60*60*24*30, secure=True, samesite='None')
        return resp

    except Exception as e:
        print("Chat Error:", e)
        return jsonify({"reply": "माफ़ करना, कुछ गड़बड़ हो गई। थोड़ी देर बाद फिर कोशिश करो।"}), 500

if __name__ == '__main__':
    debug_mode = os.getenv("DEBUG_MODE", "true").lower() == "true"
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)
