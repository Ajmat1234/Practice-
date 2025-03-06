import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from indicnlp.tokenize import indic_tokenize

app = Flask(__name__)
CORS(app)

# Indic NLP resources ka path set karo
INDIC_RESOURCES_PATH = os.environ.get("INDIC_RESOURCES_PATH", "./indic_nlp_resources")
os.environ["INDIC_RESOURCES_PATH"] = INDIC_RESOURCES_PATH

@app.route("/spell-check", methods=["POST"])
def spell_check():
    data = request.get_json()
    text = data.get("text", "")

    if not text:
        return jsonify({"error": "Text is empty"}), 400

    words = indic_tokenize.trivial_tokenize(text)
    return jsonify({"words": words})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
