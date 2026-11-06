import os
import tempfile
from pathlib import Path

import numpy as np
from scipy.io.wavfile import write
from dotenv import load_dotenv
from groq import Groq


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

MODEL_NAME = "whisper-large-v3-turbo"

client = None


def get_groq_client():
    global client

    if client is None:
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY not found in .env")

        client = Groq(api_key=GROQ_API_KEY)

    return client


def transcribe_with_groq(
    audio: np.ndarray,
    sample_rate: int,
    language: str = "ur"
) -> str:

    if audio is None or audio.size == 0:
        return ""

    temp_path = None

    try:
        audio = np.asarray(audio)

        audio = audio.astype(np.float32)

        # Increase recorded audio level
        GAIN = 5.0

        audio = np.clip(
            audio * GAIN,
            -32768,
            32767
        ).astype(np.int16)

        # Check amplified audio level
        audio_float = audio.astype(np.float32) / 32768.0

        rms = np.sqrt(np.mean(audio_float ** 2))
        peak = np.max(np.abs(audio_float))

        print(f"[AUDIO] Amplified RMS: {rms:.5f}")
        print(f"[AUDIO] Amplified Peak: {peak:.5f}")

        with tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False
        ) as temp_file:

            temp_path = temp_file.name

        write(
            temp_path,
            sample_rate,
            audio
        )

        print("\n[GROQ ASR] Sending audio for transcription...")

        groq_client = get_groq_client()

        with open(temp_path, "rb") as audio_file:

            result = groq_client.audio.transcriptions.create(
                file=audio_file,
                model=MODEL_NAME,
                language=language,
                prompt=(
                    "The speaker may use Urdu, Roman Urdu, English, "
                    "or a mixture of these languages. "
                    "Transcribe the spoken words accurately. "
                    "Preserve English technical terms and application names."
                ),
                response_format="json",
                temperature=0.0
            )

        transcript = result.text.strip()

        print(f"[GROQ ASR] Recognized: {transcript}")

        return transcript

    except Exception as error:

        print(f"[GROQ ASR ERROR] {error}")

        return ""

    finally:

        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)