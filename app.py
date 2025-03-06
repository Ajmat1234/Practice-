from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)

# CORS Fix
CORS(app, resources={r"/spell-check": {"origins": "*"}})  

wrong_words = ["गलती", "शब्द"]
correct_suggestions = {
    "गलती": ["त्रुटि", "भूल"],
    "शब्द": ["शब्दावली", "अक्षर"]
}

@app.route("/spell-check", methods=["POST"], strict_slashes=False)
def spell_check():
    try:
        data = request.get_json()
        print("Received Data:", data)  # Debugging ke liye

        text = data.get("text", "")
        if not text:
            print("Error: Text is empty")  # Debugging
            return jsonify({"error": "Text is empty"}), 400

        words = text.split(" ")
        checked_words = []

        for word in words:
            if word in wrong_words:
                checked_words.append({
                    "word": word,
                    "correct": False,
                    "suggestions": correct_suggestions.get(word, [])
                })
            else:
                checked_words.append({
                    "word": word,
                    "correct": True,
                    "suggestions": []
                })

        print("Response:", checked_words)  # Debugging ke liye
        return jsonify({"checkedText": checked_words})

    except Exception as e:
        print("Error:", str(e))  # Debugging
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))  # Default 8000 port
    app.run(host="0.0.0.0", port=port, debug=True)
