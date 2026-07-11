import pytest

from app.services.storage import detect_content_type


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (b"%PDF-1.7", "application/pdf"),
        (b"\xff\xd8\xffanything", "image/jpeg"),
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"II*\x00anything", "image/tiff"),
        (b"not-a-document", None),
    ],
)
def test_detect_content_type(
    header: bytes,
    expected: str | None,
) -> None:
    assert detect_content_type(header) == expected
