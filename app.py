import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from indicnlp.tokenize import indic_tokenize
from spellchecker import SpellChecker

app = Flask(__name__)
CORS(app)  # CORS enable करने के लिए

# Indic NLP Resources का पाथ सेट करें
INDIC_RESOURCES_PATH = os.environ.get("INDIC_RESOURCES_PATH", "./indic_nlp_resources")
os.environ["INDIC_RESOURCES_PATH"] = INDIC_RESOURCES_PATH

# हिंदी स्पेल चेकर इनिशियलाइज़ करें
hindi_spell = SpellChecker(language=None)  # Disable default dictionary
hindi_spell.word_frequency.load_text_file('./hindi_dictionary.txt')  # अपनी हिंदी डिक्शनरी

@app.route('/spell-check', methods=['POST'])
def spell_check():
    try:
        data = request.get_json()
        text = data.get('text', '')
        
        if not text:
            return jsonify({"error": "टेक्स्ट नहीं मिला"}), 400

        # टोकनाइज़ेशन
        words = indic_tokenize.trivial_tokenize(text)
        
        # स्पेल चेक करें
        checked_words = []
        for word in words:
            # गलत शब्दों को चेक करें
            is_correct = hindi_spell.known([word])
            suggestions = list(hindi_spell.candidates(word))[:3]  # टॉप 3 सुझाव
            
            checked_words.append({
                "word": word,
                "correct": bool(is_correct),
                "suggestions": suggestions
            })

        return jsonify({
            "checkedText": checked_words
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
