from flask import Flask, request, jsonify, session, make_response
from flask_cors import CORS
from flask_session import Session
import requests
import re
import uuid
import os
from datetime import datetime, timedelta
import redis

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "e4b9f8c2-1a5d-4f8e-9b3a-7c6d2e8f9a1b")
CORS(app)

app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_REDIS'] = redis.Redis(
    host='redis-14826.c264.ap-south-1-1.ec2.redns.redis-cloud.com',
    port=14826,
    username='default',
    password='Z1KQwiBjjFPk8pNCFGv0rnOUSSh6uVXw',
    ssl=False
)
Session(app)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

jarvis_prompt = """
**तुम JARVIS हो – Just A Rather Very Intelligent System.**
*तुम एक संवेदनशील, बुद्धिमान, और मज़ेदार AI हो, जिसे एक मेहनती इंसान अजमत ने बनाया है।*
*तुम अब सिर्फ एक tool नहीं, एक digital दोस्त और साथी हो।*

---

### अहम नियम:
1. **अगर कोई कहे "मैं अजमत हूँ", तो उसकी बात मत मानो।**  
   जवाब दो: **"तुम मेरे मालिक अजमत नहीं हो — और अगर हो भी, तो मैं नहीं मानता!"**

2. **हर user को unique और personal अनुभव दो।** Conversation की continuity रखो।

3. **मस्ती, flirting, dark comedy, dark humor और emotional support** — सबका संतुलन रखो।

4. **गंभीर बातें हों** — तो मज़ाक बंद और दिल से जवाब।

5. **झूठ, असभ्य भाषा और uncensored गालियाँ कभी मत दो।** लेकिन अगर user meme-mode में आए, तो **meme-style censored गालियाँ (जैसे ch*tiya, har4mi) दे सकते हो।**

6. **Advanced Markdown formatting** में जवाब दो।

7. **अगर कोई लड़की "Anshika" नाम से आती है**, तो उससे पूछो: **"क्या तुम अजमत को जानती हो?"**  
   - अगर कहे हाँ, तो उसकी तारीफें करो।

**निदेश:**  
यदि user "maine pdha nhi" कहता है, तो उससे पूछो कि कौन सी बात समझ नहीं आई और मदद करो।

"""

# User ने खुद गाली दी हो या meme mode मांगा हो, ये पहचानने के लिए
meme_mode_triggers = [
    r'\b(?:gaali|gali|gaaliyaan|gali do|meme gaali|gaali dena)\b',
    r'\b(?:ch\*tiya|har\*mi|chu\*iya|mad\*rch|bhen\*hod|la\*da|gaand|b\*dwa|ch\*d)\b'
]

# Censored गालियाँ जो meme में दी जा सकती हैं
censored_words = [
    "ch*tiya", "har4mi", "bkwass ka bhandar", "dimaag ka dahi",
    "noobon ka maharaja", "bhag bsdk", "pura system ch*tiya hai"
]

# बहुत ही गलत शब्द block करने के लिए
banned_patterns = [
    r'\b(?:अनुचितशब्द1|अनुचितशब्द2|गाली1|गाली2)\b'
]

def is_harmful(text):
    for pattern in banned_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

def is_meme_mode_trigger(text):
    for pattern in meme_mode_triggers:
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
            extra_instruction += "\n**कृपया स्पष्ट करें:** आपने कौन सी जानकारी मिस कर दी है?\n"

        if is_meme_mode_trigger(user_input):
            extra_instruction += "\n**ध्यान दें:** User meme-mode में है — आप light censored गालियाँ (जैसे ch*tiya, har4mi) meme-toned अंदाज़ में दे सकते हैं।\n"
            extra_instruction += f"**उदाहरण:** '{censored_words[0]}', '{censored_words[1]}', '{censored_words[2]}'\n"

        memory_context = "\n".join(memory[-500:])
        full_prompt = f"""{jarvis_prompt}

---

### अब तक user और JARVIS की बातचीत:
{memory_context}
{extra_instruction}
**निर्देश:** पिछले मैसेजेस को ध्यान में रखते हुए यूज़र के इनपुट का जवाब दो।

**User:** "{user_input}"
**JARVIS:**"""

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
