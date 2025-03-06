from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Frontend-backend communication allow karega

# Dummy spell checking dictionary (Baad me database ya API connect kar sakte ho)
wrong_words = ["गलती", "शब्द"]
correct_suggestions = {
    "गलती": ["त्रुटि", "भूल"],
    "शब्द": ["शब्दावली", "अक्षर"]
}

@app.route("/spell-check", methods=["POST"])
def spell_check():
    try:
        data = request.get_json()
        text = data.get("text", "")

        if not text:
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

        return jsonify({"checkedText": checked_words})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
