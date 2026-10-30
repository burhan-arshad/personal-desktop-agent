
import os
import tempfile
import numpy as np
import whisper
import sounddevice as sd
from scipy.io.wavfile import write

CHANNELS = 1
RECORD_SECONDS = 5

MIC_DEVICE = 9
SAMPLE_RATE = 48000
GAIN = 5.0
WHISPER_MODEL = "small"


print("Loading Whisper model...")
model = whisper.load_model(WHISPER_MODEL)
print("Whisper model loaded successfully.")


def record_audio(duration=RECORD_SECONDS):
    print(f"\nRecording for {duration} seconds...")
    print("Speak now!")

    try:
        audio = sd.rec(
            int(duration * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            device=MIC_DEVICE
        )

        sd.wait()

        print("Recording completed.")
        return audio

    except Exception as e:
        print(f"Microphone recording error: {e}")
        return None


def amplify_audio(audio):
    audio_float = audio.astype(np.float32)

    amplified = audio_float * GAIN

    amplified = np.clip(
        amplified,
        -32768,
        32767
    )

    return amplified.astype(np.int16)


def transcribe_audio(audio):
    if audio is None:
        return ""

    temp_path = None

    try:
        amplified_audio = amplify_audio(audio)

        audio_float = amplified_audio.astype(np.float32) / 32768.0

        rms = np.sqrt(np.mean(audio_float ** 2))
        peak = np.max(np.abs(audio_float))

        print(f"Audio RMS: {rms:.6f}")
        print(f"Audio Peak: {peak:.6f}")

        with tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False
        ) as temp_file:
            temp_path = temp_file.name

        write(temp_path, SAMPLE_RATE, amplified_audio)
        write("voice_test.wav", SAMPLE_RATE, amplified_audio)

        print("Amplified audio saved: voice_test.wav")
        print("Transcribing audio...")

        result = model.transcribe(
            temp_path,
            fp16=False,
            language="en",
            temperature=0,
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
            logprob_threshold=-1.0,
            compression_ratio_threshold=2.4
        )

        text = result["text"].strip()

        print(f"Recognized: {text}")

        return text

    except Exception as e:
        print(f"Transcription error: {e}")
        return ""

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def listen_and_transcribe(duration=RECORD_SECONDS):
    audio = record_audio(duration)

    if audio is None:
        return ""

    return transcribe_audio(audio)


if __name__ == "__main__":
    recognized_text = listen_and_transcribe()

    print("\nFinal Transcription:")
    print(recognized_text if recognized_text else "No speech recognized.")
