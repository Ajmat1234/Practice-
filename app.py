from flask import Flask, request, jsonify
import requests
from flask_cors import CORS  # <-- Yeh line add karo

app = Flask(__name__)
CORS(app)  # <-- Yeh line add karo

GEMINI_API_KEY = "AIzaSyALVGk-yBmkohV6Wqei63NARTd9xD-O7TI"

jarvis_prompt = """
तुम JARVIS हो, एक मज़ेदार और फिल्मी अंदाज में जवाब देने वाले AI...
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
