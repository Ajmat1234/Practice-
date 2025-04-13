import requests
import json
from gtts import gTTS
from moviepy.editor import *
from pathlib import Path
from flask import Flask, send_file, jsonify, request
import os
import random
import threading
import logging
from PIL import Image
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import time
from datetime import datetime, timedelta

# Flask ऐप सेटअप
app = Flask(__name__)

# लॉगिंग सेटअप
logging.basicConfig(level=logging.INFO, filename='video_generation.log', filemode='a',
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# API कीज़
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyALVGk-yBmkohV6Wqei63NARTd9xD-O7TI")
UNSPLASH_ACCESS_KEYS = [
    os.environ.get("UNSPLASH_ACCESS_KEY_1", "kNizNf9VA4QeHVzKfj4hes1UKIepoL6XLYkeGWJ1LCs"),
    os.environ.get("UNSPLASH_ACCESS_KEY_2", "zP4uEWJLAyEXFmeKbsyC9scQPkvipqClqEVxG2_rX28")
]

# API URL
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
HEADERS = {"Content-Type": "application/json"}

# आउटपुट डायरेक्टरी और फाइल्स
Path("output/videos").mkdir(parents=True, exist_ok=True)
Path("titles.txt").touch()
VIDEO_LOG_FILE = "video_log.json"
TIMESTAMP_FILE = "last_generation.json"

# ग्लोबल वैरिएबल
last_image_paths = []
generation_lock = threading.Lock()
key_quota = {0: 50, 1: 50}  # Unsplash कोटा (50 रिक्वेस्ट्स प्रति Key)

# फाइल्स को इनिशियलाइज़ करें
def init_files():
    if not os.path.exists(VIDEO_LOG_FILE):
        with open(VIDEO_LOG_FILE, "w") as f:
            json.dump({}, f)
    if not os.path.exists(TIMESTAMP_FILE):
        with open(TIMESTAMP_FILE, "w") as f:
            json.dump({"last_generation": 0}, f)

init_files()

# वीडियो लॉग को अपडेट करें
def update_video_log(video_id, title):
    with open(VIDEO_LOG_FILE, "r") as f:
        video_log = json.load(f)
    video_log[str(video_id)] = {"title": title, "timestamp": str(datetime.now())}
    with open(VIDEO_LOG_FILE, "w") as f:
        json.dump(video_log, f, indent=4)
    logger.info(f"Updated video log for Video {video_id}: {title}")

# आखिरी जनरेशन टाइम चेक करें
def can_generate():
    with open(TIMESTAMP_FILE, "r") as f:
        data = json.load(f)
    last_gen = data.get("last_generation", 0)
    current_time = time.time()
    if current_time - last_gen >= 3 * 60 * 60:  # 3 घंटे
        return True
    logger.info(f"Cannot generate yet. Wait for {3*60*60 - (current_time - last_gen)} seconds.")
    return False

# टाइमस्टैम्प अपडेट करें
def update_timestamp():
    with open(TIMESTAMP_FILE, "w") as f:
        json.dump({"last_generation": time.time()}, f)

# Unsplash से तस्वीरें लेना
def generate_dynamic_image(image_prompt, video_id):
    global last_image_paths, key_quota
    logger.info(f"[*] Generating new image for prompt: {image_prompt[:50]}... [Video {video_id}]")
    
    query = image_prompt.replace('\n', ' ').replace('  ', ' ').strip()[:50]
    
    # दोनों कीज़ को ट्राई करें
    for key_index, access_key in enumerate(UNSPLASH_ACCESS_KEYS):
        if key_quota[key_index] == 0:
            logger.info(f"Skipping Key {key_index + 1} due to zero quota [Video {video_id}]")
            continue
        
        try:
            response = requests.get(
                f"https://api.unsplash.com/photos/random?query={query}&client_id={access_key}&orientation=portrait&w=1080&h=1920",
                timeout=10
            )
            remaining = int(response.headers.get('X-Ratelimit-Remaining', '0'))
            key_quota[key_index] = remaining
            logger.info(f"Unsplash API Key {key_index + 1} remaining requests: {remaining} [Video {video_id}]")
            
            if remaining == 0:
                logger.warning(f"Key {key_index + 1} has no quota remaining [Video {video_id}]")
                continue

            if response.status_code == 200:
                image_url = response.json()['urls']['regular']
                image_path = f"output/videos/image_{video_id}_{random.randint(1, 10000)}.jpg"
                img_data = requests.get(image_url, timeout=10).content
                with open(image_path, 'wb') as handler:
                    handler.write(img_data)
                last_image_paths.append(image_path)
                logger.info(f"[✓] Image saved at {image_path} [Video {video_id}]")
                return image_path
            elif response.status_code == 403:
                logger.warning(f"Key {key_index + 1} rate limit hit [Video {video_id}]")
                key_quota[key_index] = 0
                continue
            else:
                logger.error(f"Unsplash API Key {key_index + 1} returned status {response.status_code}: {response.text} [Video {video_id}]")
                continue
        except Exception as e:
            logger.error(f"Unsplash API Key {key_index + 1} failed: {str(e)} [Video {video_id}]")
            continue
    
    # अगर कोटा खत्म हो, तो 1 घंटे वेट करें
    logger.warning(f"All keys have no quota, waiting 3600 seconds... [Video {video_id}]")
    time.sleep(3600)
    key_quota.update({0: 50, 1: 50})  # कोटा रीसेट (Unsplash हर घंटे रीसेट होता है)
    return generate_dynamic_image(image_prompt, video_id)  # दोबारा ट्राई करें

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

# YouTube पर अपलोड और फाइल डिलीट
def upload_to_youtube(video_path, video_id):
    try:
        youtube = youtube_service()
        if not youtube:
            logger.error("YouTube service not available")
            return False

        if not os.path.exists(video_path):
            logger.error(f"Video file {video_path} does not exist")
            return False

        metadata_path = f"output/videos/metadata_number_{video_id}.json"
        if not os.path.exists(metadata_path):
            logger.error(f"Metadata file {metadata_path} not found")
            return False

        with open(metadata_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        request_body = {
            "snippet": {
                "title": meta.get("title", f"Video {video_id}"),
                "description": meta.get("description", "No description"),
                "categoryId": "24"
            },
            "status": {"privacyStatus": "public"}
        }

        media = MediaFileUpload(video_path)
        youtube.videos().insert(part="snippet,status", body=request_body, media_body=media).execute()
        logger.info(f"[✓] Uploaded video {video_id} to YouTube")

        # पुरानी फाइल्स डिलीट
        try:
            for file in os.listdir("output/videos"):
                file_path = os.path.join("output/videos", file)
                if os.path.isfile(file_path) and file.startswith(("video_", "audio_", "image_", "metadata_")):
                    os.remove(file_path)
                    logger.info(f"Deleted old file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to delete old files: {str(e)}")

        try:
            os.remove(video_path)
            logger.info(f"Deleted local video file {video_path}")
        except Exception as e:
            logger.warning(f"Failed to delete video file {video_path}: {str(e)}")

        return True

    except Exception as e:
        logger.error(f"Upload failed for Video {video_id}: {str(e)}")
        return False

# स्क्रिप्ट और इमेज प्रॉम्प्ट्स जनरेट करने का फंक्शन
def generate_script_and_prompts(video_id, min_duration=45, max_duration=70, adjust_for_duration=None):
    try:
        # अगर ऑडियो लंबा या छोटा है, तो प्रॉम्प्ट को एडजस्ट करें
        prompt_text = (
            f"Generate a detailed and engaging script in English about history, facts, or science for a {min_duration} to {max_duration}-second video. "
            "Divide the script into 10-15 short sections, each with 10-12 words for a unique image prompt for Unsplash. "
            "Ensure total script duration is between {min_duration} and {max_duration} seconds when spoken. "
        )
        if adjust_for_duration == "shorter":
            prompt_text += "Make the script shorter to reduce audio duration. "
        elif adjust_for_duration == "longer":
            prompt_text += "Make the script longer to increase audio duration. "
        
        prompt_text += (
            "Format: Title: [title]\nDescription: [description]\nScript Section 1: [script_section_1]\nImage Prompt 1: [image_prompt_1]\n"
            "Script Section 2: [script_section_2]\nImage Prompt 2: [image_prompt_2]\n... up to Script Section 15: [script_section_15]\n"
            "Image Prompt 15: [image_prompt_15]"
        )
        
        prompt = {
            "contents": [{
                "parts": [{
                    "text": prompt_text
                }]
            }]
        }

        response = requests.post(GEMINI_URL, headers=HEADERS, json=prompt, timeout=30)
        if response.status_code != 200:
            logger.error(f"Gemini API failed for Video {video_id}: {response.text}")
            raise Exception("Gemini API failed")

        content = response.json()['candidates'][0]['content']['parts'][0]['text']
        lines = [line.strip() for line in content.split("\n") if line.strip()]
        
        title = next((line.split("Title:")[1].strip() for line in lines if "Title:" in line), f"Amazing Story #{video_id}")
        description = next((line.split("Description:")[1].strip() for line in lines if "Description:" in line), "A fascinating journey!")
        
        script_sections = []
        image_prompts = []
        for i in range(1, 16):  # 15 सेक्शन तक चेक
            script_key = f"Script Section {i}"
            prompt_key = f"Image Prompt {i}"
            script = next((line.split(f"{script_key}:")[1].strip() for line in lines if f"{script_key}:" in line), None)
            prompt = next((line.split(f"{prompt_key}:")[1].strip() for line in lines if f"{prompt_key}:" in line), None)
            if script and prompt:
                script_sections.append(script)
                image_prompts.append(prompt)
            else:
                break

        if not script_sections:
            logger.error("No script sections found")
            script_sections = ["Discover fascinating history facts here!"] * 10
            image_prompts = ["history illustration"] * 10

        return title, description, script_sections, image_prompts

    except Exception as e:
        logger.error(f"Script generation failed for Video {video_id}: {str(e)}")
        raise

# वीडियो जेनरेशन फंक्शन
def generate_video(video_id):
    with generation_lock:
        try:
            logger.info(f"[*] Starting generation of Video {video_id}...")

            # स्क्रिप्ट और इमेज प्रॉम्प्ट्स जनरेट करना
            max_attempts = 3
            attempt = 0
            adjust_for_duration = None
            while attempt < max_attempts:
                title, description, script_sections, image_prompts = generate_script_and_prompts(video_id, adjust_for_duration=adjust_for_duration)
                
                # मेटाडेटा सेव करना
                metadata_path = f"output/videos/metadata_number_{video_id}.json"
                try:
                    with open(metadata_path, "w", encoding="utf-8") as f:
                        json.dump({"title": title, "description": description}, f)
                except Exception as e:
                    logger.error(f"Failed to save metadata: {str(e)}")
                    raise Exception("Metadata save failed")

                # ऑडियो बनाना
                full_script = ". ".join(script_sections) + "."
                try:
                    tts = gTTS(text=full_script, lang='en', slow=False)
                    audio_path = f"output/videos/audio_{video_id}.mp3"
                    tts.save(audio_path)
                    if not os.path.exists(audio_path):
                        logger.error(f"Audio file {audio_path} not generated")
                        raise Exception("Audio generation failed")
                except Exception as e:
                    logger.error(f"Audio generation failed: {str(e)}")
                    raise Exception("Audio generation failed")

                # ऑडियो की अवधि प्राप्त करें
                try:
                    audio_clip = AudioFileClip(audio_path)
                    total_audio_duration = audio_clip.duration
                    logger.info(f"Total audio duration: {total_audio_duration} seconds")
                    
                    # ऑडियो ड्यूरेशन चेक
                    if 45 <= total_audio_duration <= 70:
                        logger.info("Audio duration is within acceptable range (45-70 seconds)")
                        break
                    else:
                        logger.warning(f"Audio duration {total_audio_duration} is out of range (45-70 seconds), retrying...")
                        adjust_for_duration = "shorter" if total_audio_duration > 70 else "longer"
                        attempt += 1
                        continue
                except Exception as e:
                    logger.error(f"Failed to load audio clip: {str(e)}")
                    raise Exception("Audio clip loading failed")
            
            if attempt >= max_attempts:
                logger.error(f"Failed to generate acceptable audio duration after {max_attempts} attempts")
                raise Exception("Audio duration adjustment failed")

            logger.info(f"Title: {title}")
            logger.info(f"Script Sections: {script_sections}")
            logger.info(f"Image Prompts: {image_prompts}")

            # तस्वीरें जेनरेट करना
            global last_image_paths
            last_image_paths = []
            for i, prompt in enumerate(image_prompts[:15]):  # ठीक 15 इमेज
                image_path = generate_dynamic_image(prompt, video_id)
                if not image_path:
                    logger.error(f"Failed to generate image for prompt: {prompt} [Video {video_id}]")
                    raise Exception("Image generation failed")
            
            # सुनिश्चित करें कि ठीक 15 इमेज हैं
            if len(last_image_paths) < 15:
                logger.warning(f"Only {len(last_image_paths)} images generated, filling with defaults [Video {video_id}]")
                while len(last_image_paths) < 15:
                    default_image = f"output/videos/default_{video_id}_{random.randint(1, 10000)}.jpg"
                    with open(default_image, 'wb') as handler:
                        handler.write(requests.get("https://images.unsplash.com/photo-1514477917009-4f4c4b9dd4eb", timeout=10).content)
                    last_image_paths.append(default_image)
                    logger.info(f"[✓] Used default image {default_image} [Video {video_id}]")

            # वीडियो क्लिप्स बनाना
            clips = []
            section_duration = total_audio_duration / len(script_sections)
            section_durations = [section_duration] * len(script_sections)

            # तस्वीरों और टेक्स्ट को क्लिप्स में जोड़ना
            for i, (script, image_path, duration) in enumerate(zip(script_sections, last_image_paths, section_durations)):
                try:
                    img_clip = ImageClip(image_path).set_duration(duration).set_start(sum(section_durations[:i]))
                    text_clip = TextClip(script, fontsize=50, color='white', font='Arial-Bold', size=(900, 200))
                    text_clip = text_clip.set_start(sum(section_durations[:i])).set_duration(duration).set_position((0.1, 0.85))
                    clips.extend([img_clip, text_clip])
                except Exception as e:
                    logger.error(f"Failed to create clip for section {i+1}: {str(e)} [Video {video_id}]")
                    raise Exception("Clip creation failed")

            # वीडियो बनाना
            try:
                video = CompositeVideoClip(clips).set_audio(audio_clip.set_duration(total_audio_duration))
                video_path = f"output/videos/video_{video_id}.mp4"
                logger.info(f"Starting video rendering for Video {video_id}...")
                video.write_videofile(video_path, fps=24, codec='libx264', preset='ultrafast', threads=4)
                logger.info(f"[✓] Video saved at {video_path}")
            except Exception as e:
                logger.error(f"Video rendering failed: {str(e)} [Video {video_id}]")
                raise Exception("Video rendering failed")

            # YouTube पर अपलोड
            try:
                if not upload_to_youtube(video_path, video_id):
                    logger.error("YouTube upload failed, keeping video file [Video {video_id}]")
                    return {"id": video_id, "path": video_path}
            except Exception as e:
                logger.error(f"YouTube upload failed for Video {video_id}: {str(e)}")
                return {"id": video_id, "path": video_path}

            # टाइटल और वीडियो लॉग अपडेट
            try:
                with open("titles.txt", "a", encoding="utf-8") as f:
                    f.write(f"{video_id}: {title}\n")
                logger.info(f"Title saved for Video {video_id}: {title}")
                update_video_log(video_id, title)
            except Exception as e:
                logger.error(f"Failed to save title for Video {video_id}: {str(e)}")

            update_timestamp()  # जनरेशन के बाद टाइमस्टैम्प अपडेट
            return {"id": video_id, "path": video_path}

        except Exception as e:
            logger.error(f"Error in video generation for Video {video_id}: {str(e)}")
            return None

# Flask रूट्स
@app.route('/')
def index():
    return jsonify(message="Video generation API is running. Use /generate to start.")

@app.route('/generate')
def generate():
    if not can_generate():
        return jsonify(error="Cannot generate yet. Please wait."), 429
    try:
        video_id = random.randint(1, 10000)
        threading.Thread(target=generate_video, args=(video_id,), daemon=True).start()
        logger.info(f"Generation triggered for Video {video_id}")
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
    if os.path.exists('video_generation.log'):
        with open('video_generation.log', 'r') as f:
            logs = f.read()
        return jsonify({"logs": logs})
    return jsonify({"error": "Logs not found"}), 404

@app.route('/video_log')
def video_log():
    if os.path.exists(VIDEO_LOG_FILE):
        with open(VIDEO_LOG_FILE, 'r') as f:
            return jsonify(json.load(f))
    return jsonify({"error": "Video log not found"}), 404

# पिंग सिस्टम (Render.com को एक्टिव रखने के लिए)
def keep_alive():
    try:
        while True:
            response = requests.get("https://work-4ec6.onrender.com", timeout=10)
            logger.info(f"Ping sent to keep server alive, status: {response.status_code}")
            time.sleep(300)  # हर 5 मिनट में पिंग
    except Exception as e:
        logger.error(f"Ping failed: {str(e)}")

# ऑटोमैटिक जनरेशन
def trigger_generation():
    try:
        time.sleep(10)  # शुरू में 10 सेकंड का इंतज़ार
        while True:
            if can_generate():
                with generation_lock:
                    response = requests.get("https://work-4ec6.onrender.com/generate", timeout=10)
                    if response.status_code == 200:
                        logger.info("Automatic generation triggered successfully")
                    else:
                        logger.error(f"Automatic generation failed with status {response.status_code}: {response.text}")
            time.sleep(300)  # हर 5 मिनट में चेक करें
    except Exception as e:
        logger.error(f"Automatic generation failed: {str(e)}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=trigger_generation, daemon=True).start()
    app.run(host="0.0.0.0", port=port)
