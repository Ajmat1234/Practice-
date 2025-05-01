from flask import Flask, request, jsonify
import os
import logging
import logging.config
import yaml
from scripts.generate_audio import generate_coqui_audio
from threading import Lock

app = Flask(__name__)
generation_lock = Lock()

# Setup logging
with open("logging_config.yaml", "r") as f:
    config = yaml.safe_load(f.read())
    logging.config.dictConfig(config)

logger = logging.getLogger("audioGenLogger")

# Ensure output directory exists
os.makedirs("output/audio", exist_ok=True)

@app.route("/generate_audio", methods=["POST"])
def generate_audio():
    try:
        with generation_lock:
            data = request.get_json()
            if not data or "text" not in data or "video_id" not in data:
                logger.error("Invalid request: 'text' and 'video_id' are required")
                return jsonify({"error": "Invalid request: 'text' and 'video_id' are required"}), 400

            text = data["text"]
            video_id = data["video_id"]

            logger.info(f"[*] Starting audio generation for Video {video_id}")
            audio_path = generate_coqui_audio(text, video_id)
            logger.info(f"[*] Audio generation completed for Video {video_id}")

            return jsonify({
                "status": "success",
                "video_id": video_id,
                "audio_path": audio_path
            }), 200

    except Exception as e:
        logger.error(f"Generation failed for Video {video_id}: {str(e)}")
        return jsonify({"error": f"Generation failed: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
