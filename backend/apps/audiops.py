import asyncio
from pathlib import Path

from google.cloud import texttospeech

from backend.core.storage import storage_manager
from backend.core.logging import get_logger

log = get_logger(__name__)


def text_to_audio_sync(text_block: str, slide_number: int, output_dir: Path) -> Path:
    tts_client = texttospeech.TextToSpeechClient()
    synthesis_input = texttospeech.SynthesisInput({"text": text_block})
    voice = texttospeech.VoiceSelectionParams(
        {"language_code": "en-US", "name": "en-US-Standard-H"}
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        effects_profile_id=["small-bluetooth-speaker-class-device"],
        speaking_rate=1,
        pitch=1,
    )

    response = tts_client.synthesize_speech(
        input=synthesis_input, voice=voice, audio_config=audio_config
    )
    output_path = output_dir / f"{slide_number}.mp3"

    with open(output_path, "wb") as out:
        out.write(response.audio_content)

    return output_path


def generate_audio_files_sync(
    session_id: str, explanations_json: dict[str, str]
) -> list[Path]:
    audio_dir = storage_manager.get_temp_audio_dir(session_id)
    generated_files = []

    for i, key in enumerate(explanations_json, 1):
        text = explanations_json[key]
        if text and text.strip():
            audio_path = text_to_audio_sync(text, i, audio_dir)
            generated_files.append(audio_path)

    log.info("audio files generated", session_id=session_id, count=len(generated_files))
    return generated_files


async def text_to_audio(text_block: str, slide_number: int, output_dir: Path) -> Path:
    return await asyncio.to_thread(
        text_to_audio_sync, text_block, slide_number, output_dir
    )


async def generate_audio_files(
    session_id: str, explanations_json: dict[str, str]
) -> list[Path]:
    audio_dir = storage_manager.get_temp_audio_dir(session_id)
    generated_files = []

    tasks = []
    for i, key in enumerate(explanations_json, 1):
        text = explanations_json[key]
        if text and text.strip():
            tasks.append(text_to_audio(text, i, audio_dir))

    results = await asyncio.gather(*tasks)
    generated_files = list(results)

    log.info("audio files generated", session_id=session_id, count=len(generated_files))
    return generated_files
