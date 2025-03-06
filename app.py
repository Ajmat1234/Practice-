import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from indicnlp.tokenize import indic_tokenize
from hindi_spellchecker import correct_sentence  # Hindi Spell Checker

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

    words = indic_tokenize.trivial_tokenize(text)  # Words split karna
    corrected_text = correct_sentence(text)  # Spell checking

    checked_words = []
    for word in words:
        if word in corrected_text:  # Agar word sahi hai
            checked_words.append({"word": word, "correct": True, "suggestions": []})
        else:  # Agar word galat hai, to correct word suggest karo
            checked_words.append({"word": word, "correct": False, "suggestions": [corrected_text]})

    return jsonify({"checkedText": checked_words})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
