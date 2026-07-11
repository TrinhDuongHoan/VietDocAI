from datetime import UTC, datetime

from celery.exceptions import SoftTimeLimitExceeded
from celery.utils.log import get_task_logger

from app.db.models import Document
from app.db.session import SessionLocal
from app.services.ocr import run_ocr
from app.worker.celery_app import celery_app


logger = get_task_logger(__name__)


def utc_now() -> datetime:
    return datetime.now(UTC)


@celery_app.task(
    bind=True,
    name="ocr.process_document",
    max_retries=3,
    acks_late=True,
)
def process_document(
    self,
    document_id: str,
) -> dict[str, str]:
    db = SessionLocal()

    try:
        document = db.get(Document, document_id)

        if document is None:
            logger.warning(
                "Document %s không tồn tại.",
                document_id,
            )
            return {
                "document_id": document_id,
                "status": "not_found",
            }

        # Task có thể được gửi lại khi worker bị restart.
        if document.status == "completed":
            return {
                "document_id": document_id,
                "status": "completed",
            }

        document.status = "processing"
        document.error_message = None
        document.processing_started_at = utc_now()
        document.completed_at = None
        document.failed_at = None
        db.commit()

        logger.info(
            "Bắt đầu OCR document %s.",
            document_id,
        )

        result = run_ocr(document.storage_path)

        document.result = result
        document.status = "completed"
        document.model_name = "PaddleOCR"
        document.model_version = result["ocr_version"]
        document.error_message = None
        document.completed_at = utc_now()
        document.failed_at = None

        db.commit()

        logger.info(
            "OCR document %s hoàn tất.",
            document_id,
        )

        return {
            "document_id": document_id,
            "status": "completed",
        }

    except SoftTimeLimitExceeded:
        db.rollback()
        document = db.get(Document, document_id)

        if document is not None:
            document.status = "failed"
            document.error_message = "OCR vượt quá thời gian xử lý cho phép."
            document.failed_at = utc_now()
            db.commit()

        logger.exception("OCR document %s bị timeout.", document_id)
        raise

    except Exception as exc:
        db.rollback()

        document = db.get(Document, document_id)

        if self.request.retries < self.max_retries:
            if document is not None:
                document.status = "retrying"
                document.error_message = str(exc)
                document.failed_at = None
                db.commit()

            countdown = 2 ** (self.request.retries + 1)

            logger.exception(
                "OCR lỗi, chuẩn bị retry document %s.",
                document_id,
            )

            raise self.retry(
                exc=exc,
                countdown=countdown,
            )

        if document is not None:
            document.status = "failed"
            document.error_message = str(exc)
            document.failed_at = utc_now()
            db.commit()

        logger.exception(
            "OCR document %s thất bại.",
            document_id,
        )

        raise

    finally:
        db.close()
