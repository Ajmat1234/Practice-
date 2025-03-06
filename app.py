from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app, resources={r"/spell-check": {"origins": "*"}})

@app.route("/spell-check", methods=["POST"], strict_slashes=False)
def spell_check():
    try:
        data = request.get_json()
        text = data.get("text", "")

        if not text:
            return jsonify({"error": "Text is empty"}), 400

        api_url = "https://api.languagetool.org/v2/check"
        params = {"text": text, "language": "hi"}
        response = requests.post(api_url, data=params)

        if response.status_code != 200:
            return jsonify({"error": "LanguageTool API failed"}), 500

        matches = response.json().get("matches", [])
        checked_words = []

        for match in matches:
            checked_words.append({
                "word": match.get("context", {}).get("text", ""),
                "correct": False,
                "suggestions": [sug["value"] for sug in match.get("replacements", [])]
            })

        return jsonify({"checkedText": checked_words})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
