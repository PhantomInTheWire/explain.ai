import logging
from pathlib import Path

from google.cloud import texttospeech

from backend.core.storage import storage_manager

logger = logging.getLogger(__name__)


def text_to_audio(text_block: str, slide_number: int, output_dir: Path) -> Path:
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


async def generate_audio_files(
    session_id: str, explanations_json: dict[str, str]
) -> list[Path]:
    audio_dir = storage_manager.get_temp_audio_dir(session_id)
    generated_files = []

    for i, key in enumerate(explanations_json, 1):
        text = explanations_json[key]
        if text and text.strip():
            audio_path = text_to_audio(text, i, audio_dir)
            generated_files.append(audio_path)

    logger.info(
        f"Generated {len(generated_files)} audio files for session {session_id}"
    )
    return generated_files
