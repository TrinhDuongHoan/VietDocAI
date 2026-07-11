from pathlib import Path
import shutil
import subprocess
import tempfile

from PIL import Image, ImageSequence


IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
}


def create_preview_image(
    source_path: Path,
    content_type: str,
) -> tuple[Path, str, str | None]:
    if content_type in IMAGE_CONTENT_TYPES:
        return source_path, content_type, None

    if content_type == "image/tiff":
        return create_tiff_preview(source_path)

    if content_type == "application/pdf":
        return create_pdf_preview(source_path)

    raise ValueError("Không hỗ trợ preview loại file này.")


def create_tiff_preview(source_path: Path) -> tuple[Path, str, str]:
    temporary_directory = tempfile.mkdtemp(prefix="vietdoc-preview-")
    preview_path = Path(temporary_directory) / "preview.png"

    try:
        with Image.open(source_path) as image:
            first_frame = next(ImageSequence.Iterator(image))
            first_frame.convert("RGB").save(preview_path, format="PNG")

    except Exception:
        shutil.rmtree(temporary_directory, ignore_errors=True)
        raise

    return preview_path, "image/png", temporary_directory


def create_pdf_preview(source_path: Path) -> tuple[Path, str, str]:
    temporary_directory = tempfile.mkdtemp(prefix="vietdoc-preview-")
    output_prefix = Path(temporary_directory) / "page"

    try:
        subprocess.run(
            [
                "pdftoppm",
                "-f",
                "1",
                "-singlefile",
                "-png",
                "-r",
                "144",
                str(source_path),
                str(output_prefix),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )

        preview_path = output_prefix.with_suffix(".png")

        if not preview_path.exists():
            raise RuntimeError("Không tạo được ảnh preview từ PDF.")

    except Exception:
        shutil.rmtree(temporary_directory, ignore_errors=True)
        raise

    return preview_path, "image/png", temporary_directory
