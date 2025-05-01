import os
import logging
from TTS.api import TTS
import backoff

logger = logging.getLogger("audioGenLogger")

# Initialize Coqui TTS model for Hindi
try:
    # Try multilingual model with Hindi support
    tts_model = TTS(model_name="tts_models/multilingual/multi-dataset/your_tts", progress_bar=True, gpu=False)
    logger.info("Loaded multilingual YourTTS model for Hindi")
except Exception as e:
    logger.warning(f"Failed to load YourTTS model: {str(e)}. Falling back to Vakyansh model")
    # Fallback to Vakyansh model (pre-downloaded or custom)
    try:
        tts_model = TTS(model_path="vakyansh-tts/hi/vakyansh", config_path="vakyansh-tts/hi/config.json", progress_bar=True, gpu=False)
        logger.info("Loaded Vakyansh Hindi model")
    except Exception as e:
        logger.error(f"Failed to load Vakyansh model: {str(e)}")
        raise

@backoff.on_exception(backoff.expo, (Exception,), max_tries=3)
def generate_coqui_audio(text, video_id):
    try:
        logger.info(f"Generating Hindi audio for Video {video_id} using Coqui TTS")
        audio_path = f"output/audio/audio_{video_id}_full.wav"

        # Add manual pauses for suspenseful effect
        text_with_pauses = text.replace("।", "। [500ms] ")

        # Generate audio with customized settings for suspenseful tone
        tts_model.tts_to_file(
            text=text_with_pauses,
            file_path=audio_path,
            speaker_wav=None,
            language="hi",
            speed=0.85,  # Slower for dramatic effect
            pitch=0.7,   # Lower pitch for intensity
            energy=1.3   # Higher energy for suspense
        )

        # Convert WAV to MP3 using pydub
        from pydub import AudioSegment
        mp3_path = audio_path.replace(".wav", ".mp3")
        audio = AudioSegment.from_wav(audio_path)
        audio.export(mp3_path, format="mp3", bitrate="192k")
        os.remove(audio_path)  # Remove WAV to save space

        logger.info(f"Full audio generated at {mp3_path}")
        return mp3_path

    except Exception as e:
        logger.error(f"Failed to generate Coqui TTS audio: {str(e)}")
        raise
