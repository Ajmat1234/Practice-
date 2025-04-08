from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)

# CORS setup for frontend
CORS(app, supports_credentials=True, origins=[
    "https://work-lyart-rho.vercel.app",
    "https://work-ajmat1234s-projects.vercel.app"
])

JARVIS_PROMPT = """
तुम JARVIS हो – Just A Rather Very Intelligent System।  
मुझे हिंदी में लिखे हुए डॉक्यूमेंट्स दिए जाएंगे, जिनमें टाइपिंग मिस्टेक्स हो सकती हैं। तुम्हारा काम है:  
1. सिर्फ उन शब्दों को सुधारना जो टाइपिंग मिस्टेक की वजह से गलत हैं।  
2. किसी भी वाक्य को बदलना नहीं है, न ही कोई नया टेक्स्ट जोड़ना या हटाना।  
3. पूरा डॉक्यूमेंट वैसे का वैसा रखना, बस गलत शब्दों को ठीक करना।  
4. सुधार के बाद पूरा डॉक्यूमेंट मुझे वापस भेजना।  
"""

@app.route('/')
def home():
    return 'JARVIS backend is live!'

@app.route('/chat', methods=['POST'])
def chat():
    try:
        user_input = request.json.get("message")
        if user_input.strip().lower() == "wake up":
            return jsonify({"reply": "Backend is awake!"})

        full_prompt = f"""{JARVIS_PROMPT}

        मेरा डॉक्यूमेंट:
        {user_input}

        सुधार के बाद पूरा डॉक्यूमेंट लौटाएं।
        """

        response = requests.post(
            "https://work-4ec6.onrender.com/gpt",
            json={"message": full_prompt},
            timeout=60  # Increased timeout
        )

        result = response.json()
        reply = result.get("reply", "कोई जवाब नहीं मिला।")

        return jsonify({"reply": reply})

    except Exception as e:
        print("Error:", e)
        return jsonify({"reply": "सर्वर में कोई गड़बड़ हुई। थोड़ी देर बाद फिर से कोशिश करें।"}), 500

if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
