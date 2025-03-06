import requests

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

        matches = response.json()["matches"]
        checked_words = []

        for match in matches:
            checked_words.append({
                "word": match["context"]["text"],
                "correct": False,
                "suggestions": match["replacements"]
            })

        return jsonify({"checkedText": checked_words})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
