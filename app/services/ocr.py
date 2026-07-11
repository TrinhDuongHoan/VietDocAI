from pathlib import Path
from typing import Any

from app.core.config import get_settings


settings = get_settings()

_ocr_pipeline: Any | None = None


def get_ocr_pipeline() -> Any:
    global _ocr_pipeline

    if _ocr_pipeline is None:
        # Import tại worker khi thật sự cần dùng.
        # API container không phải khởi tạo model.
        from paddleocr import PaddleOCR

        _ocr_pipeline = PaddleOCR(
            lang=settings.ocr_language,
            ocr_version=settings.ocr_version,
            device=settings.ocr_device,
            cpu_threads=settings.ocr_cpu_threads,

            # Hữu ích với ảnh chụp điện thoại.
            use_doc_orientation_classify=True,
            use_textline_orientation=True,

            # Tắt tạm thời để giảm tài nguyên ở Sprint 1.
            use_doc_unwarping=False,
        )

    return _ocr_pipeline


def to_python_value(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()

    if isinstance(value, dict):
        return {
            key: to_python_value(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [to_python_value(item) for item in value]

    if isinstance(value, tuple):
        return [to_python_value(item) for item in value]

    return value


def extract_result_payload(result: Any) -> dict[str, Any]:
    raw_result = getattr(result, "json", None)

    if callable(raw_result):
        raw_result = raw_result()

    if not isinstance(raw_result, dict):
        raise RuntimeError(
            "PaddleOCR không trả về kết quả JSON hợp lệ."
        )

    raw_result = to_python_value(raw_result)

    # Kết quả thường có dạng {"res": {...}}.
    payload = raw_result.get("res", raw_result)

    if not isinstance(payload, dict):
        raise RuntimeError("OCR payload không hợp lệ.")

    return payload


def run_ocr(file_path: str) -> dict[str, Any]:
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {file_path}")

    pipeline = get_ocr_pipeline()
    predictions = pipeline.predict(str(path))

    pages: list[dict[str, Any]] = []
    document_text_parts: list[str] = []
    all_scores: list[float] = []

    for default_page_index, prediction in enumerate(predictions):
        payload = extract_result_payload(prediction)

        texts = payload.get("rec_texts") or []
        scores = payload.get("rec_scores") or []
        boxes = (
            payload.get("rec_boxes")
            or payload.get("rec_polys")
            or []
        )

        lines: list[dict[str, Any]] = []

        for index, text in enumerate(texts):
            score = (
                float(scores[index])
                if index < len(scores)
                else None
            )

            box = (
                boxes[index]
                if index < len(boxes)
                else None
            )

            if score is not None:
                all_scores.append(score)

            lines.append(
                {
                    "text": str(text),
                    "confidence": score,
                    "box": to_python_value(box),
                }
            )

        page_text = "\n".join(
            line["text"]
            for line in lines
            if line["text"].strip()
        )

        document_text_parts.append(page_text)

        page_index = payload.get("page_index")

        if page_index is None:
            page_index = default_page_index

        pages.append(
            {
                "page_index": page_index,
                "text": page_text,
                "lines": lines,
            }
        )

    average_confidence = None

    if all_scores:
        average_confidence = sum(all_scores) / len(all_scores)

    return {
        "engine": "PaddleOCR",
        "ocr_version": settings.ocr_version,
        "language": settings.ocr_language,
        "device": settings.ocr_device,
        "page_count": len(pages),
        "average_confidence": average_confidence,
        "full_text": "\n\n".join(document_text_parts),
        "pages": pages,
    }