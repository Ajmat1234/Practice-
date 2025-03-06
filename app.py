from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Ye frontend-backend communication allow karega

# Dummy spell checking dictionary (Baad me database ya API connect kar sakte ho)
wrong_words = ["गलती", "शब्द"]
correct_suggestions = {
    "गलती": ["त्रुटि", "भूल"],
    "शब्द": ["शब्दावली", "अक्षर"]
}

@app.route("/spell-check", methods=["POST"])
def spell_check():
    data = request.json
    text = data.get("text", "")

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

if __name__ == "__main__":
    app.run(debug=True)
