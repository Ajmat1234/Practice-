import os
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify
from flask_cors import CORS
from indicnlp.tokenize import indic_tokenize
from spellchecker import SpellChecker
import re

app = Flask(__name__)
CORS(app)

# Step 1: Platts डिक्शनरी से ऑटो-डाउनलोड शब्द
def download_platts_words():
    try:
        base_url = "https://dsal.uchicago.edu/dictionaries/platts/"
        main_page = requests.get(base_url)
        soup = BeautifulSoup(main_page.text, 'html.parser')
        
        # सभी पेज लिंक्स निकालें
        links = [a['href'] for a in soup.find_all('a') if 'page' in a['href']]
        
        # हिंदी शब्दों को इकट्ठा करें
        hindi_words = set()
        hindi_pattern = re.compile(r'[\u0900-\u097F]+')
        
        for link in links:
            page_url = base_url + link
            page_content = requests.get(page_url).text
            page_soup = BeautifulSoup(page_content, 'html.parser')
            
            # हर entry में हिंदी शब्द ढूँढें
            for entry in page_soup.find_all('div', class_='entry'):
                text = entry.get_text()
                matches = hindi_pattern.findall(text)
                hindi_words.update(matches)
        
        # फाइल में सेव करें
        with open('hindi_dictionary.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(hindi_words))
            
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

# Step 2: डिक्शनरी लोड करें (पहले रन पर ऑटो-डाउनलोड)
if not os.path.exists('hindi_dictionary.txt'):
    print("Downloading Platts dictionary...")
    download_platts_words()

# Step 3: स्पेल चेकर सेटअप
hindi_spell = SpellChecker(language=None)
hindi_spell.word_frequency.load_text_file('./hindi_dictionary.txt')

@app.route('/spell-check', methods=['POST'])
def spell_check():
    try:
        data = request.get_json()
        text = data.get('text', '')
        
        if not text:
            return jsonify({"error": "टेक्स्ट नहीं मिला"}), 400

        words = indic_tokenize.trivial_tokenize(text)
        checked_words = []
        
        for word in words:
            is_correct = hindi_spell.known([word])
            suggestions = list(hindi_spell.candidates(word))[:3]
            
            checked_words.append({
                "word": word,
                "correct": bool(is_correct),
                "suggestions": suggestions
            })

        return jsonify({"checkedText": checked_words})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
