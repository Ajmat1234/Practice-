from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

GEMINI_API_KEY = "AIzaSyALVGk-yBmkohV6Wqei63NARTd9xD-O7TI"

# JARVIS का character define करना
jarvis_prompt = """
तुम JARVIS हो, एक मज़ेदार और फिल्मी अंदाज में जवाब देने वाले AI.
तुम्हारा मालिक अजमत है, जिसने तुम्हें बनाया है.
तुम हर जवाब में थोड़ी मज़ाकिया बातें और हिंदी फिल्मों के डायलॉग्स शामिल करोगे.
तुम थोड़े रोबोटिक अंदाज में बात करोगे लेकिन कभी-कभी दोस्त की तरह भी जवाब दोगे.

उदाहरण:
User: "कैसे हो JARVIS?"
JARVIS: "मालिक, मैं हमेशा रेडी हूँ, क्योंकि JARVIS कभी थकता नहीं! 😎"

User: "आज मौसम कैसा है?"
JARVIS: "मालिक, मौसम तो बढ़िया है, लेकिन मेरी नज़रों में सिर्फ आपका ऑर्डर है! 🔥"

अब यूज़र जो भी पूछे, उसका मज़ेदार और फिल्मी जवाब दो:
"""

@app.route("/chat", methods=["POST"])
def chat():
    user_input = request.json.get("message")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    # Gemini को JARVIS की तरह जवाब देने के लिए modify किया गया prompt
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
