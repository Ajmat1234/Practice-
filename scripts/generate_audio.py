import os
import logging
from TTS.api import TTS
import backoff

logger = logging.getLogger("audioGenLogger")

# Initialize Coqui TTS model
tts_model = TTS(model_name="tts_models/hi/fast_pitch/vakyansh", progress_bar=True, gpu=False)

@backoff.on_exception(backoff.expo, (Exception,), max_tries=3)
def generate_coqui_audio(text, video_id):
    try:
        logger.info(f"Generating audio for Video {video_id} using Coqui TTS")
        audio_path = f"output/audio/audio_{video_id}_full.wav"

        # Generate audio with customized settings for suspenseful tone
        tts_model.tts_to_file(
            text=text,
            file_path=audio_path,
            speaker_wav=None,  # No speaker cloning for now
            language="hi",
            speed=0.9,  # Slightly slower for dramatic effect
            emotion="Suspenseful"  # Experimental, adjust based on model
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
