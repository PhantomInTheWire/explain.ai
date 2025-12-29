import asyncio
from pathlib import Path
from typing import Optional

from google.cloud import texttospeech_v1

from core.storage import storage_manager
from core.logging import get_logger

log = get_logger(__name__)

_tts_client: Optional[texttospeech_v1.TextToSpeechAsyncClient] = None


async def get_tts_client() -> texttospeech_v1.TextToSpeechAsyncClient:
    global _tts_client
    if _tts_client is None:
        _tts_client = texttospeech_v1.TextToSpeechAsyncClient()
        log.debug("tts client initialized")
    return _tts_client


async def close_tts_client() -> None:
    global _tts_client
    if _tts_client is not None:
        await _tts_client.close()
        _tts_client = None
        log.debug("tts client closed")


async def text_to_audio(text_block: str, slide_number: int, output_dir: Path) -> Path:
    client = await get_tts_client()

    synthesis_input = texttospeech_v1.SynthesisInput(text=text_block)
    voice = texttospeech_v1.VoiceSelectionParams(
        language_code="en-US", name="en-US-Standard-H"
    )
    audio_config = texttospeech_v1.AudioConfig(
        audio_encoding=texttospeech_v1.AudioEncoding.MP3,
        effects_profile_id=["small-bluetooth-speaker-class-device"],
        speaking_rate=1.0,
        pitch=1.0,
    )

    response = await client.synthesize_speech(
        input=synthesis_input, voice=voice, audio_config=audio_config
    )

    output_path = output_dir / f"{slide_number}.mp3"

    async def _write_audio():
        with open(output_path, "wb") as out:
            out.write(response.audio_content)

    await asyncio.to_thread(_write_audio)

    return output_path


async def generate_audio_files(
    session_id: str, explanations_json: dict[str, str]
) -> list[Path]:
    audio_dir = storage_manager.get_temp_audio_dir(session_id)

    tasks = []
    for i, key in enumerate(explanations_json, 1):
        text = explanations_json[key]
        if text and text.strip():
            tasks.append(text_to_audio(text, i, audio_dir))

    generated_files = await asyncio.gather(*tasks)

    log.info("audio files generated", session_id=session_id, count=len(generated_files))
    return list(generated_files)
