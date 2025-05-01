from flask import Flask, request, jsonify, send_file
import os
import logging
import logging.config
import yaml
from scripts.generate_audio import generate_espeak_audio
from threading import Lock

app = Flask(__name__)
generation_lock = Lock()

# Ensure log directory exists
log_dir = "output"
os.makedirs(log_dir, exist_ok=True)

# Setup logging
try:
    with open("logging_config.yaml", "r") as f:
        config = yaml.safe_load(f.read())
        logging.config.dictConfig(config)
except Exception as e:
    # Fallback to basic logging if config fails
    logging.basicConfig(level=logging.INFO)
    logging.error(f"Failed to load logging config: {str(e)}")

logger = logging.getLogger("audioGenLogger")

# Ensure audio output directory exists
os.makedirs("output/audio", exist_ok=True)

@app.route("/ping", methods=["GET"])
def ping():
    logger.info("Ping received, service is alive")
    return jsonify({"status": "alive"}), 200

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
            audio_path = generate_espeak_audio(text, video_id)
            logger.info(f"[*] Audio generation completed for Video {video_id}")

            return jsonify({
                "status": "success",
                "video_id": video_id,
                "audio_path": audio_path
            }), 200

    except Exception as e:
        logger.error(f"Generation failed for Video {video_id}: {str(e)}")
        return jsonify({"error": f"Generation failed: {str(e)}"}), 500

@app.route("/download_audio/<video_id>", methods=["GET"])
def download_audio(video_id):
    try:
        audio_path = f"output/audio/audio_{video_id}_full.mp3"
        if not os.path.exists(audio_path):
            logger.error(f"Audio file not found for Video {video_id}")
            return jsonify({"error": "Audio file not found"}), 404
        return send_file(audio_path, as_attachment=True)
    except Exception as e:
        logger.error(f"Failed to download audio for Video {video_id}: {str(e)}")
        return jsonify({"error": f"Download failed: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
