from flask import Flask, request, jsonify
from flask_cors import CORS
import hunspell

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests

# Load Hunspell dictionary
h = hunspell.HunSpell('/usr/share/hunspell/hi_IN.dic', '/usr/share/hunspell/hi_IN.aff')

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
            if not h.spell(word):  # If word is incorrect
                suggestions = h.suggest(word)
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
