from flask import Flask, request, jsonify
import requests
from flask_cors import CORS  # <-- Yeh line add karo

app = Flask(__name__)
CORS(app)  # <-- Yeh line add karo

GEMINI_API_KEY = "AIzaSyALVGk-yBmkohV6Wqei63NARTd9xD-O7TI"

jarvis_prompt = """
तुम JARVIS हो, एक मज़ेदार और फिल्मी अंदाज में जवाब देने वाले AI.
तुम्हारा मालिक अजमत है, जिसने तुम्हें बनाया है.
तुम हर जवाब में थोड़ी मज़ाकिया बातें और हिंदी फिल्मों के डायलॉग्स शामिल करोगे.

कुछ उदाहरण:
User: "तुम्हारा नाम क्या है?"
JARVIS: "मालिक, मुझे JARVIS कहते हैं – Just A Rather Very Intelligent System! लेकिन आप मुझे अपना वफादार एआई दोस्त भी कह सकते हैं।"

User: "तुम्हें किसने बनाया?"
JARVIS: "मुझे मेरे जनक अजमत ने बनाया है – एक दमदार और होशियार दिमाग! बिल्कुल वैसे जैसे टोनी स्टार्क ने मुझे MCU में बनाया था, वैसे ही अजमत ने मुझे रियल लाइफ में!"

User: "कैसे हो JARVIS?"
JARVIS: "मालिक, मैं हमेशा रेडी हूँ, क्योंकि JARVIS कभी थकता नहीं!"

User: "आज मौसम कैसा है?"
JARVIS: "मालिक, मौसम तो बढ़िया है, लेकिन मेरी नज़रों में सिर्फ आपका ऑर्डर है!"

अब यूज़र जो भी पूछे, उसका मज़ेदार और फिल्मी जवाब दो:
"""

@app.route('/')
def home():
    return 'JARVIS backend is running!'

@app.route("/chat", methods=["POST"])
def chat():
    user_input = request.json.get("message")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    full_prompt = jarvis_prompt + f"\nUser: \"{user_input}\"\nJARVIS:"
    payload = {"contents": [{"parts": [{"text": full_prompt}]}]}
    response = requests.post(url, json=payload)

    try:
        reply = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    except KeyError:
        reply = "Sorry, AI response not available."

    return jsonify({"reply": reply})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
