from flask import Flask, send_file, jsonify, request
from pathlib import Path
import os
import requests
import json
import random
import threading
import logging
from gtts import gTTS
from moviepy.editor import *
from PIL import Image
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import time
from datetime import datetime, timedelta
from difflib import SequenceMatcher
import redis

# Flask ऐप सेटअप
app = Flask(__name__)

# लॉगिंग सेटअप
logging.basicConfig(level=logging.INFO, filename='video_generation.log', filemode='a',
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# API कीज
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyALVGk-yBmkohV6Wqei63NARTd9xD-O7TI")
UNSPLASH_ACCESS_KEYS = [
    os.environ.get("UNSPLASH_ACCESS_KEY_1", "kNizNf9VA4QeHVzKfj4hes1UKIepoL6XLYkeGWJ1LCs"),
    os.environ.get("UNSPLASH_ACCESS_KEY_2", "zP4uEWJLAyEXFmeKbsyC9scQPkvipqClqEVxG2_rX28")
]

# Redis सेटअप (दूसरे कोड से लिया गया स्टाइल)
REDIS_HOST = "redis-18952.c301.ap-south-1-1.ec2.redns.redis-cloud.com"
REDIS_PORT = 18952
REDIS_USERNAME = "default"
REDIS_PASSWORD = "gZ7K1Wl6UeqmuOGTHXsnWsyXIvt1dfTb"  # सही पासवर्ड
REDIS_DB = 0  # डीबी इंडेक्स 0, जैसा दूसरे कोड में है

try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        username=REDIS_USERNAME,
        password=REDIS_PASSWORD,
        db=REDIS_DB,
        decode_responses=True,
        ssl=False  # फ्री प्लान में SSL नहीं है, जैसा दूसरे कोड में
    )
    redis_client.ping()
    logger.info("Connected to Redis successfully")
except Exception as e:
    logger.error(f"Failed to connect to Redis: {str(e)}")
    raise

# API URL
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
HEADERS = {"Content-Type": "application/json"}

# आउटपुट डायरेक्टरी
Path("output/videos").mkdir(parents=True, exist_ok=True)

# ग्लोबल वैरिएबल
generation_lock = threading.Lock()
key_quota = {0: None, 1: None}
video_count = redis_client.get("video_count") or 0

# Redis फंक्शन्स
def save_notification(message):
    try:
        redis_client.lpush("notifications", f"{datetime.utcnow().isoformat()}: {message}")
        logger.info(f"Notification saved to Redis: {message}")
    except Exception as e:
        logger.error(f"Failed to save notification: {str(e)}")

def save_topic(video_id, title):
    try:
        redis_client.set(f"topics:{video_id}", title)
        logger.info(f"Topic saved to Redis: {title}")
    except Exception as e:
        logger.error(f"Failed to save topic: {str(e)}")

def check_topic_exists(title):
    try:
        keys = redis_client.keys("topics:*")
        for key in keys:
            if redis_client.get(key).lower() == title.lower():
                return True
        return False
    except Exception as e:
        logger.error(f"Failed to check topic: {str(e)}")
        return False

def save_image_to_redis(prompt, image_url):
    try:
        redis_client.set(f"images:{prompt}", image_url)
        logger.info(f"Image saved to Redis for prompt: {prompt}")
    except Exception as e:
        logger.error(f"Failed to save image to Redis: {str(e)}")

def check_image_in_redis(prompt):
    try:
        image_url = redis_client.get(f"images:{prompt}")
        if image_url:
            logger.info(f"Found exact image in Redis for prompt: {prompt}")
            return image_url
        return None
    except Exception as e:
        logger.error(f"Failed to check image in Redis: {str(e)}")
        return None

def find_similar_image_in_redis(prompt):
    try:
        keys = redis_client.keys("images:*")
        max_similarity = 0
        best_match = None
        for key in keys:
            stored_prompt = key.replace("images:", "")
            similarity = SequenceMatcher(None, prompt.lower(), stored_prompt.lower()).ratio()
            if similarity > max_similarity and similarity > 0.7:
                max_similarity = similarity
                best_match = redis_client.get(key)
        if best_match:
            logger.info(f"Found similar image in Redis for prompt: {prompt}")
        return best_match
    except Exception as e:
        logger.error(f"Failed to find similar image in Redis: {str(e)}")
        return None

def get_random_image_from_redis():
    try:
        keys = redis_client.keys("images:*")
        if keys:
            random_key = random.choice(keys)
            image_url = redis_client.get(random_key)
            logger.info(f"Selected random image from Redis: {image_url}")
            return image_url
        return None
    except Exception as e:
        logger.error(f"Failed to get random image from Redis: {str(e)}")
        return None

def cleanup_day_end():
    global video_count
    try:
        video_count = int(redis_client.get("video_count") or 0)
        if video_count >= 3:
            keys = redis_client.keys("images:*")
            if keys:
                redis_client.delete(*keys)
                logger.info("Deleted images from Redis at day end")
            redis_client.set("video_count", 0)
            video_count = 0
    except Exception as e:
        logger.error(f"Failed to cleanup Redis: {str(e)}")

def save_generation_timestamp():
    try:
        redis_client.set("generation_log", datetime.utcnow().isoformat())
        logger.info("Generation timestamp saved to Redis")
    except Exception as e:
        logger.error(f"Failed to save generation timestamp: {str(e)}")

def check_last_generation():
    try:
        timestamp = redis_client.get("generation_log")
        if timestamp:
            last_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            time_diff = (datetime.utcnow() - last_time).total_seconds()
            return time_diff
        return float("inf")
    except Exception as e:
        logger.error(f"Failed to check last generation: {str(e)}")
        return float("inf")

# Unsplash से तस्वीरें
def generate_dynamic_image(image_prompt, video_id):
    logger.info(f"[*] Generating image for prompt: {image_prompt[:50]}...")
    query = image_prompt.replace('\n', ' ').replace('  ', ' ').strip()[:50]

    # Redis में सटीक प्रॉम्प्ट
    image_url = check_image_in_redis(query)
    if image_url:
        return image_url

    # Redis में समान प्रॉम्प्ट
    image_url = find_similar_image_in_redis(query)
    if image_url:
        return image_url

    # Unsplash API
    for key_index, access_key in enumerate(UNSPLASH_ACCESS_KEYS):
        if key_quota[key_index] == 0:
            logger.info(f"Skipping Key {key_index + 1} due to zero quota")
            continue

        try:
            response = requests.get(
                f"https://api.unsplash.com/photos/random?query={query}&client_id={access_key}&orientation=portrait&w=1080&h=1920",
                timeout=10
            )
            remaining = int(response.headers.get('X-Ratelimit-Remaining', '0'))
            key_quota[key_index] = remaining
            logger.info(f"Unsplash API Key {key_index + 1} remaining requests: {remaining}")

            if remaining == 0:
                logger.warning(f"Key {key_index + 1} has no quota remaining")
                continue

            if response.status_code == 200:
                image_url = response.json()['urls']['regular']
                save_image_to_redis(query, image_url)
                logger.info(f"[✓] Image fetched for prompt: {query}")
                return image_url
            elif response.status_code == 403:
                logger.warning(f"Key {key_index + 1} rate limit hit")
                key_quota[key_index] = 0
                continue
            else:
                logger.error(f"Unsplash API Key {key_index + 1} returned status {response.status_code}: {response.text}")
                continue
        except Exception as e:
            logger.error(f"Unsplash API Key {key_index + 1} failed: {str(e)}")
            continue

    # Redis से रैंडम इमेज
    image_url = get_random_image_from_redis()
    if image_url:
        logger.info(f"[✓] Reused random image from Redis for prompt: {query}")
        return image_url

    # डिफॉल्ट इमेज
    logger.error(f"No images available for prompt: {query}, using default image")
    default_image = "https://images.unsplash.com/photo-1514477917009-4f4c4b9dd4eb"
    save_image_to_redis(query, default_image)
    logger.info(f"[✓] Used default image for prompt: {query}")
    return default_image

# YouTube सर्विस
def youtube_service():
    try:
        token_path = "token.json"
        if os.path.exists(token_path):
            return build("youtube", "v3", credentials=Credentials.from_authorized_user_file(token_path))
        logger.warning(f"{token_path} not found, skipping YouTube upload")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize YouTube service: {str(e)}")
        return None

# YouTube अपलोड
def upload_to_youtube(video_path, video_id, title, description):
    try:
        youtube = youtube_service()
        if not youtube:
            logger.error("YouTube service not available")
            return False

        if not os.path.exists(video_path):
            logger.error(f"Video file {video_path} does not exist")
            return False

        request_body = {
            "snippet": {
                "title": title,
                "description": description,
                "categoryId": "24"
            },
            "status": {"privacyStatus": "public"}
        }

        media = MediaFileUpload(video_path)
        youtube.videos().insert(part="snippet,status", body=request_body, media_body=media).execute()
        logger.info(f"[✓] Uploaded video {video_id} to YouTube")
        save_notification(f"Video {video_id} uploaded successfully")
        return True
    except Exception as e:
        logger.error(f"Upload failed for Video {video_id}: {str(e)}")
        return False

# स्क्रिप्ट और प्रॉम्प्ट्स
def generate_script_and_prompts(video_id, min_duration=45, max_duration=70):
    try:
        prompt_text = (
            f"Generate a detailed and engaging script in English about history, facts, or science for a {min_duration} to {max_duration}-second video. "
            "Ensure the script duration is approximately 60 seconds when spoken. "
            "Divide the script into 10-15 short sections, each with 10-12 words for a unique image prompt for Unsplash. "
            "Ensure the topic is unique and not previously used. "
            "Format: Title: [title]\nDescription: [description]\nScript Section 1: [script_section_1]\nImage Prompt 1: [image_prompt_1]\n"
            "Script Section 2: [script_section_2]\nImage Prompt 2: [image_prompt_2]\n... up to Script Section 15: [script_section_15]\n"
            "Image Prompt 15: [image_prompt_15]"
        )

        max_attempts = 2
        attempt = 0
        while attempt < max_attempts:
            response = requests.post(GEMINI_URL, headers=HEADERS, json={"contents": [{"parts": [{"text": prompt_text}]}]}, timeout=30)
            if response.status_code != 200:
                logger.error(f"Gemini API failed for Video {video_id}: {response.text}")
                attempt += 1
                continue

            content = response.json()['candidates'][0]['content']['parts'][0]['text']
            lines = [line.strip() for line in content.split("\n") if line.strip()]

            title = next((line.split("Title:")[1].strip() for line in lines if "Title:" in line), f"Amazing Story #{video_id}")
            description = next((line.split("Description:")[1].strip() for line in lines if "Description:" in line), "A fascinating journey!")

            if check_topic_exists(title):
                logger.warning(f"Topic '{title}' already exists, retrying...")
                attempt += 1
                continue

            script_sections = []
            image_prompts = []
            for i in range(1, 16):
                script_key = f"Script Section {i}"
                prompt_key = f"Image Prompt {i}"
                script = next((line.split(f"{script_key}:")[1].strip() for line in lines if f"{script_key}:" in line), None)
                prompt = next((line.split(f"{prompt_key}:")[1].strip() for line in lines if f"{prompt_key}:" in line), None)
                if script and prompt:
                    script_sections.append(script)
                    image_prompts.append(prompt)
                else:
                    break

            if len(script_sections) >= 10:
                return title, description, script_sections, image_prompts

            logger.warning(f"Insufficient script sections for Video {video_id}, retrying...")
            attempt += 1

        logger.error(f"Failed to generate valid script after {max_attempts} attempts")
        raise Exception("Script generation failed")
    except Exception as e:
        logger.error(f"Script generation failed for Video {video_id}: {str(e)}")
        raise

# वीडियो जनरेशन
def generate_video(video_id):
    global video_count
    try:
        with generation_lock:
            logger.info(f"[*] Starting generation of Video {video_id}...")
            save_notification(f"Generation started for Video {video_id}")

            # स्क्रिप्ट और प्रॉम्प्ट्स
            max_attempts = 3
            attempt = 0
            while attempt < max_attempts:
                title, description, script_sections, image_prompts = generate_script_and_prompts(video_id)

                # ऑडियो
                full_script = ". ".join(script_sections) + "."
                audio_path = f"output/videos/audio_{video_id}.mp3"
                try:
                    tts = gTTS(text=full_script, lang='en', slow=False)
                    tts.save(audio_path)
                    if not os.path.exists(audio_path):
                        logger.error(f"Audio file {audio_path} not generated")
                        raise Exception("Audio generation failed")
                except Exception as e:
                    logger.error(f"Audio generation failed: {str(e)}")
                    raise Exception("Audio generation failed")

                # ऑडियो ड्यूरेशन
                try:
                    audio_clip = AudioFileClip(audio_path)
                    total_audio_duration = audio_clip.duration
                    logger.info(f"Total audio duration: {total_audio_duration} seconds")

                    if total_audio_duration < 45 or total_audio_duration > 70:
                        logger.warning(f"Audio duration {total_audio_duration} is out of range (45-70 seconds), retrying...")
                        attempt += 1
                        continue
                    else:
                        logger.info("Audio duration is within acceptable range (45-70 seconds)")
                        break
                except Exception as e:
                    logger.error(f"Failed to load audio clip: {str(e)}")
                    raise Exception("Audio clip loading failed")

            if attempt >= max_attempts:
                logger.error(f"Failed to generate acceptable audio duration after {max_attempts} attempts")
                raise Exception("Audio duration adjustment failed")

            logger.info(f"Title: {title}")
            logger.info(f"Script Sections: {script_sections}")
            logger.info(f"Image Prompts: {image_prompts}")

            # इमेज जनरेशन
            image_urls = []
            for prompt in image_prompts:
                image_url = generate_dynamic_image(prompt, video_id)
                if not image_url:
                    logger.error(f"Failed to generate image for prompt: {prompt}")
                    raise Exception("Image generation failed")
                image_urls.append(image_url)

            # वीडियो क्लिप्स
            clips = []
            section_duration = total_audio_duration / len(script_sections)
            section_durations = [section_duration] * len(script_sections)

            for i, (script, image_url, duration) in enumerate(zip(script_sections, image_urls, section_durations)):
                try:
                    img_data = requests.get(image_url, timeout=10).content
                    img_path = f"output/videos/temp_image_{video_id}_{i}.jpg"
                    with open(img_path, 'wb') as handler:
                        handler.write(img_data)
                    img_clip = ImageClip(img_path).set_duration(duration).set_start(sum(section_durations[:i]))
                    text_clip = TextClip(script, fontsize=50, color='white', font='Arial-Bold', size=(900, 200))
                    text_clip = text_clip.set_start(sum(section_durations[:i])).set_duration(duration).set_position((0.1, 0.85))
                    clips.extend([img_clip, text_clip])
                except Exception as e:
                    logger.error(f"Failed to create clip for section {i+1}: {str(e)}")
                    raise Exception("Clip creation failed")

            # वीडियो रेंडरिंग
            video_path = f"output/videos/video_{video_id}.mp4"
            try:
                video = CompositeVideoClip(clips).set_audio(audio_clip.set_duration(total_audio_duration))
                logger.info(f"Starting video rendering for Video {video_id}...")
                video.write_videofile(video_path, fps=24, codec='libx264', preset='ultrafast', threads=4)
                logger.info(f"[✓] Video saved at {video_path}")
            except Exception as e:
                logger.error(f"Video rendering failed: {str(e)}")
                raise Exception("Video rendering failed")

            # YouTube अपलोड
            try:
                if upload_to_youtube(video_path, video_id, title, description):
                    redis_client.incr("video_count")
                    video_count = int(redis_client.get("video_count"))
                    save_topic(video_id, title)
                    cleanup_day_end()
                    try:
                        os.remove(video_path)
                        logger.info(f"Deleted local video file {video_path}")
                    except Exception as e:
                        logger.warning(f"Failed to delete video file {video_path}: {str(e)}")
                else:
                    logger.error("YouTube upload failed, keeping video file")
                    return {"id": video_id, "path": video_path}
            except Exception as e:
                logger.error(f"YouTube upload failed for Video {video_id}: {str(e)}")
                return {"id": video_id, "path": video_path}

            return {"id": video_id, "path": video_path}

    except Exception as e:
        logger.error(f"Error in video generation for Video {video_id}: {str(e)}")
        save_notification(f"Generation failed for Video {video_id}: {str(e)}")
        return None
    finally:
        try:
            for file in os.listdir("output/videos"):
                if file.startswith(("audio_", "temp_image_")):
                    os.remove(os.path.join("output/videos", file))
                    logger.info(f"Deleted temp file: {file}")
        except Exception as e:
            logger.warning(f"Failed to cleanup temp files: {str(e)}")

# Flask रूट्स
@app.route('/')
def index():
    return jsonify(message="Video generation API is running. Use /generate to start.")

@app.route('/generate')
def generate():
    try:
        time_diff = check_last_generation()
        if time_diff < 10800:
            logger.info(f"Skipping generation, last generation was {time_diff} seconds ago")
            return jsonify(message=f"Generation skipped, wait {10800 - time_diff} seconds")

        video_id = random.randint(1, 10000)
        threading.Thread(target=generate_video, args=(video_id,), daemon=True).start()
        save_generation_timestamp()
        return jsonify(message=f"Generation started for video {video_id}")
    except Exception as e:
        logger.error(f"Failed to start generation: {str(e)}")
        return jsonify(error="Failed to start generation"), 500

@app.route('/video/<int:video_id>')
def get_video(video_id):
    path = f"output/videos/video_{video_id}.mp4"
    if os.path.exists(path):
        return send_file(path)
    return jsonify(error="Video not found"), 404

@app.route('/logs')
def get_logs():
    try:
        if os.path.exists('video_generation.log'):
            with open('video_generation.log', 'r', encoding='utf-8') as f:
                logs = f.read()
            return jsonify({"logs": logs})
        return jsonify({"error": "Logs not found"}), 404
    except Exception as e:
        logger.error(f"Failed to read logs: {str(e)}")
        return jsonify({"error": "Failed to read logs"}), 500

# पिंग सिस्टम
def keep_alive():
    try:
        while True:
            requests.get("https://work-4ec6.onrender.com", timeout=10)
            logger.info("Ping sent to keep server alive")
            time.sleep(300)
    except Exception as e:
        logger.error(f"Ping failed: {str(e)}")

# ऑटोमैटिक जनरेशन
def trigger_generation():
    try:
        time.sleep(10)
        global video_count
        last_day = datetime.now().day
        while True:
            current_day = datetime.now().day
            if current_day != last_day:
                redis_client.set("video_count", 0)
                video_count = 0
                last_day = current_day

            if video_count < 3:
                time_diff = check_last_generation()
                if time_diff >= 10800:
                    with generation_lock:
                        response = requests.get("https://work-4ec6.onrender.com/generate", timeout=10)
                        if response.status_code == 200:
                            logger.info("Automatic generation triggered successfully")
                        else:
                            logger.error(f"Automatic generation failed with status {response.status_code}: {response.text}")
                else:
                    logger.info(f"Skipping generation, last generation was {time_diff} seconds ago")
            time.sleep(300)
    except Exception as e:
        logger.error(f"Automatic generation failed: {str(e)}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=trigger_generation, daemon=True).start()
    app.run(host="0.0.0.0", port=port)
