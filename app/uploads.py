"""Helpers for validating and storing uploaded images.

Uploaded files live under ``app/static/uploads`` so they can be served by
Flask's normal static route. Only real image files with an allowed extension
are accepted, and every stored file gets a random name.
"""
from pathlib import Path
from uuid import uuid4

from flask import current_app

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

# The first bytes of the file must match one of the supported image formats.
_IMAGE_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
)


class ImageUploadError(ValueError):
    """Raised when an uploaded file is not a supported image."""


def _upload_root():
    return Path(current_app.static_folder) / "uploads"


def _is_supported_image(header):
    if any(header.startswith(signature) for signature, _ in _IMAGE_SIGNATURES):
        return True
    # WEBP files start with "RIFF" and contain "WEBP" at byte offset 8.
    return header[:4] == b"RIFF" and header[8:12] == b"WEBP"


def save_image(file_storage, folder):
    """Validate and save an uploaded image, returning its static path.

    ``folder`` is a sub-directory of ``static/uploads`` (for example
    ``products`` or ``business``). Returns ``None`` when no file was supplied.
    """
    if file_storage is None or not file_storage.filename:
        return None

    extension = Path(file_storage.filename).suffix.lower().lstrip(".")
    if extension not in ALLOWED_EXTENSIONS:
        raise ImageUploadError("Use a PNG, JPG, GIF or WEBP image.")

    header = file_storage.stream.read(16)
    file_storage.stream.seek(0)
    if not _is_supported_image(header):
        raise ImageUploadError("The uploaded file is not a valid image.")

    target_dir = _upload_root() / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}.{extension}"
    file_storage.save(target_dir / filename)
    return f"uploads/{folder}/{filename}"


def delete_image(relative_path):
    """Delete a previously stored image if it is inside the uploads folder."""
    if not relative_path:
        return
    upload_root = _upload_root().resolve()
    path = (Path(current_app.static_folder) / relative_path).resolve()
    if upload_root in path.parents and path.is_file():
        path.unlink()
