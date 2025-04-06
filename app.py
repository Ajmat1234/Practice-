from flask import Flask, request, jsonify, session, make_response, render_template_string
from flask_cors import CORS
import requests
import re
import uuid
import os
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "random_secret_key_for_session"
CORS(app)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

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

3. **मस्ती, flirting, dark humor और emotional support** — सबका संतुलन रखना है।

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

---

**कृपया अपने जवाब को उपरोक्त फॉर्मेटिंग में प्रस्तुत करें।**
"""

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
        if datetime.utcnow() - last_active > timedelta(hours=1):
            memory = []
    return memory

def update_memory(memory):
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
            memory.append({"role": "user", "text": user_input})

        # Create structured Gemini contents
        contents = [{"role": "user", "parts": [{"text": jarvis_prompt}]}]

        for m in memory:
            contents.append({
                "role": m["role"],
                "parts": [{"text": m["text"]}]
            })

        contents.append({
            "role": "user",
            "parts": [{"text": user_input}]
        })

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        payload = {"contents": contents}
        response = requests.post(url, json=payload, timeout=10)
        reply = response.json()["candidates"][0]["content"]["parts"][0]["text"]

        memory.append({"role": "model", "text": reply})
        if len(memory) > 20:
            memory = memory[-20:]

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
