import os
import logging
import subprocess
from pydub import AudioSegment

logger = logging.getLogger("audioGenLogger")

def generate_espeak_audio(text, video_id):
    try:
        logger.info(f"Generating Hindi audio for Video {video_id} using eSpeak NG")
        audio_path = f"output/audio/audio_{video_id}_full.wav"

        # Add manual pauses for suspenseful effect
        text_with_pauses = text.replace("।", "। ")

        # Generate audio with eSpeak NG
        subprocess.run([
            "espeak-ng",
            "-v", "hi",  # Hindi voice
            "-s", "130",  # Speed (slower for dramatic effect)
            "-p", "40",   # Pitch (lower for intensity)
            "-w", audio_path,
            text_with_pauses
        ], check=True)

        # Convert WAV to MP3 using pydub
        mp3_path = audio_path.replace(".wav", ".mp3")
        audio = AudioSegment.from_wav(audio_path)
        audio.export(mp3_path, format="mp3", bitrate="192k")
        os.remove(audio_path)  # Remove WAV to save space

        logger.info(f"Full audio generated at {mp3_path}")
        return mp3_path

    except Exception as e:
        logger.error(f"Failed to generate eSpeak NG audio: {str(e)}")
        raise
