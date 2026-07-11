from celery import Celery

from app.core.config import get_settings


settings = get_settings()

celery_app = Celery(
    "vietdoc_ai",
    broker=settings.celery_broker_url,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    timezone="Asia/Ho_Chi_Minh",
    enable_utc=True,

    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    task_soft_time_limit=settings.celery_task_soft_time_limit,
    task_time_limit=settings.celery_task_time_limit,

    # Worker chỉ nhận một OCR job tại một thời điểm.
    worker_prefetch_multiplier=1,

    broker_connection_retry_on_startup=True,
    broker_heartbeat=30,
)
