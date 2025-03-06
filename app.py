from flask import Flask, request, jsonify
from flask_cors import CORS
import language_tool_python

app = Flask(__name__)
CORS(app, resources={r"/spell-check": {"origins": "*"}})

tool = language_tool_python.LanguageTool('hi')  # Hindi ke liye

@app.route("/spell-check", methods=["POST"], strict_slashes=False)
def spell_check():
    try:
        data = request.get_json()
        text = data.get("text", "")

        if not text:
            return jsonify({"error": "Text is empty"}), 400

        matches = tool.check(text)
        checked_words = []

        for match in matches:
            checked_words.append({
                "word": match.context,
                "correct": False,
                "suggestions": match.replacements
            })

        return jsonify({"checkedText": checked_words})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
