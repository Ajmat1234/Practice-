from flask import Flask, request, jsonify
from flask_cors import CORS
from indicnlp.tokenize import indic_tokenize

app = Flask(__name__)
CORS(app)

@app.route("/spell-check", methods=["POST"], strict_slashes=False)
def spell_check():
    try:
        data = request.get_json()
        text = data.get("text", "")

        if not text:
            return jsonify({"error": "Text is empty"}), 400

        words = indic_tokenize.trivial_tokenize(text)
        checked_words = []

        # Dummy spell-check logic (Proper dictionary required)
        for word in words:
            if word == "स्पेल्ल":
                checked_words.append({
                    "word": word,
                    "correct": False,
                    "suggestions": ["स्पेल"]
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
