import logging
import shutil
from pathlib import Path
from typing import Optional

from backend.core.config import settings

logger = logging.getLogger(__name__)


class StorageManager:
    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or settings.data_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _session_dir(self, session_id: str) -> Path:
        return self.base_dir / session_id

    def _uploads_dir(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "uploads"

    def _output_dir(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "output"

    def _temp_dir(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "temp"

    def _images_dir(self, session_id: str) -> Path:
        return self._temp_dir(session_id) / "images"

    def _audio_dir(self, session_id: str) -> Path:
        return self._temp_dir(session_id) / "audio"

    def create_session_directories(self, session_id: str) -> dict[str, Path]:
        dirs = {
            "session": self._session_dir(session_id),
            "uploads": self._uploads_dir(session_id),
            "output": self._output_dir(session_id),
            "temp": self._temp_dir(session_id),
            "images": self._images_dir(session_id),
            "audio": self._audio_dir(session_id),
        }
        for path in dirs.values():
            path.mkdir(parents=True, exist_ok=True)
        return dirs

    def delete_session_directory(self, session_id: str) -> bool:
        session_dir = self._session_dir(session_id)
        if not session_dir.exists():
            return False
        shutil.rmtree(session_dir)
        logger.info(f"Deleted session directory: {session_id}")
        return True

    def session_exists(self, session_id: str) -> bool:
        return self._session_dir(session_id).exists()

    def get_upload_path(self, session_id: str, filename: str = "source.pdf") -> Path:
        return self._uploads_dir(session_id) / filename

    def get_output_path(self, session_id: str, filename: str) -> Path:
        return self._output_dir(session_id) / filename

    def get_temp_images_dir(self, session_id: str) -> Path:
        path = self._images_dir(session_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_temp_audio_dir(self, session_id: str) -> Path:
        path = self._audio_dir(session_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def save_upload(
        self, session_id: str, file_content: bytes, filename: str = "source.pdf"
    ) -> Path:
        self.create_session_directories(session_id)
        file_path = self.get_upload_path(session_id, filename)
        with open(file_path, "wb") as f:
            f.write(file_content)
        logger.info(f"Saved upload: {file_path}")
        return file_path

    def get_file(self, session_id: str, filename: str) -> Optional[Path]:
        for path in [
            self.get_output_path(session_id, filename),
            self.get_upload_path(session_id, filename),
        ]:
            if path.exists():
                return path
        return None

    def list_output_files(self, session_id: str) -> list[str]:
        output_dir = self._output_dir(session_id)
        return (
            [f.name for f in output_dir.iterdir() if f.is_file()]
            if output_dir.exists()
            else []
        )

    def clean_temp_files(self, session_id: str) -> None:
        temp_dir = self._temp_dir(session_id)
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
            temp_dir.mkdir(parents=True, exist_ok=True)

    def list_sessions(self) -> list[str]:
        if not self.base_dir.exists():
            return []
        return [
            d.name
            for d in self.base_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ]


storage_manager = StorageManager()
