from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings


settings = get_settings()

ALLOWED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".pdf",
    ".tif",
    ".tiff",
}

EXTENSION_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".pdf": "application/pdf",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


@dataclass(frozen=True)
class StoredFile:
    path: str
    content_type: str
    size: int


def detect_content_type(header: bytes) -> str | None:
    if header.startswith(b"%PDF-"):
        return "application/pdf"

    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"

    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"

    if header.startswith(b"II*\x00") or header.startswith(b"MM\x00*"):
        return "image/tiff"

    return None


async def save_upload(file: UploadFile) -> StoredFile:
    original_filename = file.filename or "unnamed"
    suffix = Path(original_filename).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Chỉ hỗ trợ JPG, JPEG, PNG, TIFF và PDF.",
        )

    upload_directory = Path(settings.upload_dir)
    upload_directory.mkdir(parents=True, exist_ok=True)

    stored_name = f"{uuid4()}{suffix}"
    destination = upload_directory / stored_name

    maximum_size = settings.max_upload_mb * 1024 * 1024
    total_size = 0
    header = b""

    try:
        with destination.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                total_size += len(chunk)

                if total_size > maximum_size:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=(
                            f"File vượt quá giới hạn "
                            f"{settings.max_upload_mb} MB."
                        ),
                    )

                if len(header) < 16:
                    required = 16 - len(header)
                    header += chunk[:required]

                output.write(chunk)

        if total_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File rỗng.",
            )

        detected_type = detect_content_type(header)
        expected_type = EXTENSION_MIME_TYPES[suffix]

        if detected_type is None or detected_type != expected_type:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Nội dung file không khớp với phần mở rộng.",
            )

        return StoredFile(
            path=str(destination),
            content_type=detected_type,
            size=total_size,
        )

    except Exception:
        destination.unlink(missing_ok=True)
        raise

    finally:
        await file.close()