from flask import Flask, request, jsonify, send_file
import os
import redis
import logging
from pathlib import Path
from gtts import gTTS, gTTSError
import backoff
import threading
import time
import requests

app = Flask(__name__)

# Create output directory before logging setup
Path("output").mkdir(parents=True, exist_ok=True)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    filename='output/audio_gen_detailed.log',
    filemode='a',
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('audioGenLogger')

# Redis setup
REDIS_HOST = "redis-10583.c301.ap-south-1-1.ec2.redns.redis-cloud.com"
REDIS_PORT = 10583
REDIS_PASSWORD = "qBXuT3Fb37eRsVn55NWCbYCcbgV1T8oL"
try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        decode_responses=True,
        ssl=False
    )
    redis_client.ping()
    logger.info("Connected to Redis successfully")
except Exception as e:
    logger.error(f"Failed to connect to Redis: {str(e)}")
    raise

# Output directory for audio files
Path("output/audio").mkdir(parents=True, exist_ok=True)

# Stay Alive Feature
def keep_alive():
    """Background thread to ping the /ping endpoint every 5 minutes to keep the service alive."""
    while True:
        try:
            # Use the Render.com URL to ping the service
            response = requests.post("https://practice-a69v.onrender.com/ping", timeout=10)
            if response.status_code == 200:
                logger.info("Stay alive ping successful")
            else:
                logger.error(f"Stay alive ping failed with status {response.status_code}")
        except Exception as e:
            logger.error(f"Stay alive ping failed: {str(e)}")
        # Wait for 5 minutes (300 seconds)
        time.sleep(300)

# Start the keep-alive thread
threading.Thread(target=keep_alive, daemon=True).start()
logger.info("Started keep-alive thread")

@app.route('/ping', methods=['POST'])
def ping():
    logger.info("Ping received, service is alive")
    return jsonify({"status": "success", "message": "Service is alive"})

@backoff.on_exception(backoff.expo, (gTTSError, Exception), max_tries=5)
@app.route('/generate_audio', methods=['POST'])
def generate_audio():
    data = request.get_json()
    text = data.get('text')
    video_id = data.get('video_id')
    
    if not text or not video_id:
        logger.error("Missing text or video_id in request")
        return jsonify({"status": "error", "message": "Missing text or video_id"}), 400
    
    logger.info(f"[*] Starting audio generation for Video {video_id}")
    logger.info(f"Generating Hindi audio for Video {video_id} using gTTS")
    
    output_path = f"output/audio/audio_{video_id}_full.mp3"
    
    try:
        tts = gTTS(text=text, lang='hi', slow=True)
        tts.save(output_path)
        
        # Set Redis key with TTL (3600 seconds = 1 hour)
        redis_client.setex(f"audio:{video_id}", 3600, output_path)
        logger.info(f"Full audio generated at {output_path} with TTL of 3600 seconds")
        logger.info(f"[*] Audio generation completed for Video {video_id}")
        return jsonify({"status": "success", "message": "Audio generated"})
    except gTTSError as e:
        if "429" in str(e):
            logger.error(f"gTTS rate limit hit for Video {video_id}")
            return jsonify({"status": "error", "message": "Rate limit exceeded"}), 429
        logger.error(f"Failed to generate audio for Video {video_id}: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    except Exception as e:
        logger.error(f"Failed to generate audio for Video {video_id}: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/download_audio/<video_id>', methods=['GET'])
def download_audio(video_id):
    try:
        output_path = redis_client.get(f"audio:{video_id}")
        if not output_path or not os.path.exists(output_path):
            logger.error(f"Audio file not found for Video {video_id}")
            return jsonify({"status": "error", "message": "Audio file not found"}), 404
        
        logger.info(f"Downloading audio for Video {video_id} from {output_path}")
        return send_file(output_path, as_attachment=True)
    except Exception as e:
        logger.error(f"Failed to download audio for Video {video_id}: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
