from datetime import UTC, datetime
import shutil
from pathlib import Path
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.api.security import require_api_key
from app.core.config import get_settings
from app.db.models import Document
from app.db.session import get_db
from app.services.preview import create_preview_image
from app.services.storage import save_upload
from app.worker.tasks import process_document


router = APIRouter(
    prefix="/api/v1/documents",
    tags=["documents"],
)


class DocumentCreatedResponse(BaseModel):
    document_id: str
    status: str


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    content_type: str
    file_size: int
    status: str

    model_name: str | None
    model_version: str | None

    result: dict[str, Any] | None
    error_message: str | None
    processing_started_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None


def get_document_or_404(
    db: Session,
    document_id: str,
) -> Document:
    document = db.get(Document, document_id)

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy document.",
        )

    return document


def resolve_document_file(document: Document) -> Path:
    file_path = Path(document.storage_path).resolve()
    upload_root = Path(get_settings().upload_dir).resolve()

    if upload_root not in file_path.parents:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Đường dẫn file không hợp lệ.",
        )

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy file gốc.",
        )

    return file_path


@router.post(
    "",
    response_model=DocumentCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_document(
    file: UploadFile = File(...),
    _: None = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> DocumentCreatedResponse:
    original_filename = file.filename or "unnamed"

    stored_file = await save_upload(file)

    document = Document(
        original_filename=original_filename,
        content_type=stored_file.content_type,
        file_size=stored_file.size,
        storage_path=stored_file.path,
        status="queued",
    )

    try:
        db.add(document)
        db.commit()
        db.refresh(document)

    except Exception:
        db.rollback()
        Path(stored_file.path).unlink(missing_ok=True)
        raise

    try:
        process_document.delay(document.id)

    except Exception as exc:
        document.status = "failed"
        document.error_message = (
            f"Không thể gửi OCR job: {exc}"
        )
        document.failed_at = datetime.now(UTC)
        db.commit()
        Path(stored_file.path).unlink(missing_ok=True)

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Không thể gửi công việc sang OCR worker.",
        ) from exc

    return DocumentCreatedResponse(
        document_id=document.id,
        status=document.status,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
)
def get_document(
    document_id: str,
    _: None = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> Document:
    return get_document_or_404(db, document_id)


@router.get(
    "/{document_id}/file",
    include_in_schema=False,
)
def get_document_file(
    document_id: str,
    _: None = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> FileResponse:
    document = get_document_or_404(db, document_id)
    file_path = resolve_document_file(document)

    return FileResponse(
        path=file_path,
        media_type=document.content_type,
        filename=document.original_filename,
        content_disposition_type="inline",
    )


@router.get(
    "/{document_id}/preview",
    include_in_schema=False,
)
def get_document_preview(
    document_id: str,
    _: None = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> FileResponse:
    document = get_document_or_404(db, document_id)
    file_path = resolve_document_file(document)

    try:
        preview_path, media_type, cleanup_directory = create_preview_image(
            file_path,
            document.content_type,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Không thể tạo preview file.",
        ) from exc

    background = (
        BackgroundTask(shutil.rmtree, cleanup_directory, ignore_errors=True)
        if cleanup_directory is not None
        else None
    )

    return FileResponse(
        path=preview_path,
        media_type=media_type,
        filename=f"{document.id}-preview.png",
        content_disposition_type="inline",
        background=background,
    )


@router.get(
    "",
    response_model=list[DocumentResponse],
)
def list_documents(
    limit: int = Query(default=20, ge=1, le=100),
    _: None = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> list[Document]:
    statement = (
        select(Document)
        .order_by(Document.created_at.desc())
        .limit(limit)
    )

    return list(db.scalars(statement).all())
