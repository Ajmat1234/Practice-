from flask import Flask, request, jsonify
from flask_cors import CORS
from spellchecker import SpellChecker

app = Flask(__name__)
CORS(app)

spell = SpellChecker(language='hi')  # Hindi spell checker

@app.route("/spell-check", methods=["POST"], strict_slashes=False)
def spell_check():
    try:
        data = request.get_json()
        text = data.get("text", "")

        if not text:
            return jsonify({"error": "Text is empty"}), 400

        words = text.split()
        checked_words = []

        for word in words:
            if word not in spell:
                suggestions = list(spell.candidates(word))
                checked_words.append({
                    "word": word,
                    "correct": False,
                    "suggestions": suggestions
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
    app.run(host="0.0.0.0", port=8000, debug=True)
