from flask import Flask, request, jsonify
from flask_cors import CORS
from grammarly import Grammarly  # Grammarly API

app = Flask(__name__)
CORS(app, resources={r"/spell-check": {"origins": "*"}})  

@app.route("/spell-check", methods=["POST"], strict_slashes=False)
def spell_check():
    try:
        data = request.get_json()
        text = data.get("text", "")

        if not text:
            return jsonify({"error": "Text is empty"}), 400

        # **Grammarly API से स्पेलिंग और ग्रामर चेक करना**
        g = Grammarly()
        corrections = g.check(text)

        checked_words = []
        for correction in corrections:
            checked_words.append({
                "word": correction['word'],  
                "correct": correction['correct'],  
                "suggestions": correction['suggestions']  
            })

        return jsonify({"checkedText": checked_words})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
