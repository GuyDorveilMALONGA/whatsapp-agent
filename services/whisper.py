from groq import Groq
import os
import tempfile

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


async def transcribe_audio(audio_bytes: bytes, language: str = None) -> str:
    """Transcrit un message vocal WhatsApp via Groq Whisper"""
    try:
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            f.write(audio_bytes)
            temp_path = f.name

        with open(temp_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                file=("audio.ogg", audio_file.read()),
                model="whisper-large-v3",
                language=language,
                response_format="text"
            )

        os.unlink(temp_path)
        return transcription

    except Exception as e:
        print(f"Erreur transcription Whisper: {e}")
        return None
