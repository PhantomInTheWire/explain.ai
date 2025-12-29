import asyncio
from pathlib import Path

import moviepy.editor as mpe
import pypdfium2 as pdfium

from core.storage import storage_manager
from core.config import settings
from core.logging import get_logger

log = get_logger(__name__)


async def pdf_to_video(
    session_id: str, pdf_path: Path, output_filename: str = "video.mp4", fps: int = 1
) -> Path:
    def _generate_video():
        temp_images_dir = storage_manager.get_temp_images_dir(session_id)
        audio_dir = storage_manager.get_temp_audio_dir(session_id)
        output_path = storage_manager.get_output_path(session_id, output_filename)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        pdf = pdfium.PdfDocument(str(pdf_path))

        for i in range(len(pdf)):
            page = pdf[i]
            image = page.render(scale=4).to_pil()
            image.save(str(temp_images_dir / f"{i + 1}.jpg"))

        clips = []
        for i in range(len(pdf)):
            image_path = temp_images_dir / f"{i + 1}.jpg"
            audio_path = audio_dir / f"{i + 1}.mp3"

            if not image_path.exists() or not audio_path.exists():
                continue

            audio_clip = mpe.AudioFileClip(str(audio_path))
            image_clip = mpe.ImageClip(str(image_path), duration=audio_clip.duration)
            clips.append(image_clip.set_audio(audio_clip))

        if not clips:
            raise ValueError("No clips generated. Ensure PDF and audio files exist.")

        final_video = mpe.concatenate_videoclips(clips, method="compose")

        codec = None
        ffmpeg_params = None

        if settings.video_gpu_codec:
            codec = settings.video_gpu_codec
            log.info("using gpu codec", codec=codec)

            if "nvenc" in codec:
                ffmpeg_params = ["-preset", "p4", "-tune", "hq"]
            elif "videotoolbox" in codec:
                ffmpeg_params = ["-profile:v", "high", "-level", "4.0"]
            elif "qsv" in codec:
                ffmpeg_params = ["-preset", "veryfast", "-global_quality", "23"]
        else:
            codec = "libx264"
            log.debug("using cpu codec", codec=codec)

        final_video.write_videofile(
            str(output_path),
            fps=fps,
            codec=codec,
            ffmpeg_params=ffmpeg_params,
            logger=None,
        )

        for clip in clips:
            clip.close()
        final_video.close()

        log.info("video generated", output_path=str(output_path), codec=codec)
        return output_path

    return await asyncio.to_thread(_generate_video)
