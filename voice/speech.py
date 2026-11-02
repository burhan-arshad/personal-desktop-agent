import asyncio
import os
import tempfile

import edge_tts
import pygame


VOICE = "en-US-AriaNeural"
RATE = "+0%"
VOLUME = "+0%"


async def generate_speech(text, output_path):

    communicate = edge_tts.Communicate(
        text=text,
        voice=VOICE,
        rate=RATE,
        volume=VOLUME
    )

    await communicate.save(output_path)


def speak(text):

    if not text or not text.strip():
        return

    temp_path = None

    try:

        with tempfile.NamedTemporaryFile(
            suffix=".mp3",
            delete=False
        ) as temp_file:

            temp_path = temp_file.name

        asyncio.run(
            generate_speech(text, temp_path)
        )

        if not pygame.mixer.get_init():
            pygame.mixer.init()

        pygame.mixer.music.load(temp_path)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(20)

        pygame.mixer.music.unload()

    except Exception as error:

        print(f"[TTS ERROR] {error}")

    finally:

        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)