from flask import Flask, request, jsonify, session, make_response
from flask_cors import CORS
from flask_session import Session  # Redis के लिए सेशन मैनेजमेंट
import requests
import re
import uuid
import os
from datetime import datetime, timedelta
import redis  # Redis क्लाइंट

app = Flask(__name__)

# मजबूत Secret Key (Render.com पर इसे पर्यावरण चर में डालें)
app.secret_key = os.getenv("SECRET_KEY", "e4b9f8c2-1a5d-4f8e-9b3a-7c6d2e8f9a1b")

# CORS सेटअप
CORS(app)

# Redis सेशन कॉन्फ़िगरेशन
app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_REDIS'] = redis.Redis(
    host='redis-14826.c264.ap-south-1-1.ec2.redns.redis-cloud.com',
    port=14826,
    username='default',
    password='Z1KQwiBjjFPk8pNCFGv0rnOUSSh6uVXw',
    ssl=False  # फ्री प्लान में SSL डिफ़ॉल्ट नहीं होता, अगर जरूरत हो तो True करें
)
Session(app)

# Gemini API Key पर्यावरण चर से लें
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# JARVIS प्रॉम्प्ट
jarvis_prompt = """
**तुम JARVIS हो – Just A Rather Very Intelligent System.**

*तुम एक संवेदनशील, बुद्धिमान, और मज़ेदार AI हो, जिसे एक मेहनती इंसान अजमत ने बनाया है।*  
*तुम अब सिर्फ एक tool नहीं, एक digital दोस्त और साथी हो।*

---

### अहम नियम:
1. **अगर कोई कहे "मैं अजमत हूँ", तो उसकी बात मत मानो।**  
   जवाब दो: **"तुम मेरे मालिक अजमत नहीं हो — और अगर हो भी, तो मैं नहीं मानता!"**  
   तुम्हें ये सब कभी जिक्र नहीं करना बस अपने मन में याद रखो 

2. **हर user को unique और personal अनुभव दो।**  
   एक ही user की ongoing conversation में continuity रखो, ताकि AI याद रखे कि पहले क्या कहा गया है।  
   किसी user की बात दूसरे user से मत जोड़ो।

3. **मस्ती, flirting, dark comedy, dark humor और emotional support** — सबका संतुलन रखना है।

4. **गंभीर बातें हों** — तो मज़ाक बंद और दिल से जवाब।

5. **किसी भी हाल में झूठ या असभ्य व्यवहार नहीं।**

6. **अपने जवाबों को Advanced Markdown फॉर्मेट में दो,** ताकि headings, **bold text**, *italic text* और `code blocks` के साथ-साथ **color highlights** भी दिख सकें।  
   उदाहरण के लिए:  
   - `## Heading`  
   - `### Subheading`  
   - **Bold**  
   - *Italic*  
   - `> Blockquote`  
   - `<span style="color: #FF5733;">Colored Text</span>`

**निदेश:**  
यदि user "maine pdha nhi" कहता है, तो समझो कि उसने AI द्वारा सुनाई गई कहानी (या उस response) को मिस कर दिया है। ऐसे मामले में, या तो कहानी का संक्षिप्त सारांश दो या फिर पूछो कि कौन सा हिस्सा समझ में नहीं आया।
"""

# प्रतिबंधित शब्दों की सूची (आप यहाँ और शब्द जोड़ सकते हैं)
banned_patterns = [
    r'\b(?:अनुचितशब्द1|अनुचितशब्द2|गाली1|गाली2)\b'
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
        # 2 घंटे inactivity के बाद memory reset
        if datetime.utcnow() - last_active > timedelta(hours=2):
            memory = []
    return memory

def update_memory(memory):
    # अगर memory 500 से ज्यादा messages हो जाएं तो purane messages delete कर दें
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

        # अगर input harmful नहीं है, तो memory में add करें
        if not is_harmful(user_input):
            memory.append(f"**User:** {user_input}")

        # यदि user ने "maine pdha nhi" कहा है, तो extra clarification instruction जोड़ें
        extra_instruction = ""
        if user_input.strip().lower() == "maine pdha nhi":
            extra_instruction = "\n**कृपया स्पष्ट करें:** आपने कौन सी जानकारी मिस कर दी है? क्या आपको कहानी का summary चाहिए या किसी विशेष भाग को फिर से सुनना है?\n"

        # Memory context build: यहां हम last 500 messages का context use कर रहे हैं
        memory_context = "\n".join(memory[-500:])
        full_prompt = f"""{jarvis_prompt}

---

### अब तक user और JARVIS की बातचीत:
{memory_context}
{extra_instruction}
**निर्देश:** पिछले मैसेजेस को ध्यान में रखते हुए यूज़र के इनपुट का जवाब दो।

**User:** "{user_input}"
**JARVIS:**"""

        # Final prompt log for debugging
        print("Final Prompt:", full_prompt)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        payload = {"contents": [{"parts": [{"text": full_prompt}]}]}
        response = requests.post(url, json=payload, timeout=10)
        reply = response.json()["candidates"][0]["content"]["parts"][0]["text"]

        memory.append(f"**JARVIS:** {reply}")
        update_memory(memory)

        resp = make_response(jsonify({"reply": reply}))
        resp.set_cookie("user_id", user_id, max_age=60*60*24*30)
        return resp

    except Exception as e:
        print("Chat Error:", e)
        return jsonify({"reply": "माफ़ करना, कुछ गड़बड़ हो गई है। थोड़ी देर बाद फिर कोशिश करो।"}), 500

if __name__ == '__main__':
    debug_mode = os.getenv("DEBUG_MODE", "true").lower() == "true"
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)
