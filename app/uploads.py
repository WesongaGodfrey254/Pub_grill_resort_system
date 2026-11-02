"""Helpers for validating and storing uploaded images.

On serverless hosts the project directory is read-only and ephemeral, so image
bytes are stored in PostgreSQL and served by ``main.uploaded_file``. Only real
image files with an allowed extension are accepted, every stored file gets a
random name, and the size is capped independently of the request limit.
"""
from pathlib import Path
from uuid import uuid4

from .extensions import db
from .models import UploadedFile

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
ALLOWED_FOLDERS = {"products", "business"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024

_MIME_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
}

# The first bytes of the file must match one of the supported image formats.
_IMAGE_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
)


class ImageUploadError(ValueError):
    """Raised when an uploaded file is not a supported image."""


def _is_supported_image(header):
    if any(header.startswith(signature) for signature, _ in _IMAGE_SIGNATURES):
        return True
    # WEBP files start with "RIFF" and contain "WEBP" at byte offset 8.
    return header[:4] == b"RIFF" and header[8:12] == b"WEBP"


def save_image(file_storage, folder):
    """Validate and store an uploaded image, returning its media path.

    ``folder`` is a logical group (``products`` or ``business``). Returns
    ``None`` when no file was supplied. The record is added to the current
    database session and committed by the calling view.
    """
    if file_storage is None or not file_storage.filename:
        return None
    if folder not in ALLOWED_FOLDERS:
        raise ImageUploadError("Invalid upload destination.")

    extension = Path(file_storage.filename).suffix.lower().lstrip(".")
    if extension not in ALLOWED_EXTENSIONS:
        raise ImageUploadError("Use a PNG, JPG, GIF or WEBP image.")

    data = file_storage.stream.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageUploadError("Images must be 5 MB or smaller.")
    if not _is_supported_image(data[:16]):
        raise ImageUploadError("The uploaded file is not a valid image.")

    filename = f"{uuid4().hex}.{extension}"
    db.session.add(UploadedFile(
        folder=folder,
        filename=filename,
        mimetype=_MIME_TYPES[extension],
        data=data,
    ))
    return f"uploads/{folder}/{filename}"


def delete_image(relative_path):
    """Delete a previously stored image if it is a managed upload path."""
    if not relative_path:
        return
    parts = Path(relative_path).parts
    if len(parts) != 3 or parts[0] != "uploads":
        return
    folder, filename = parts[1], parts[2]
    record = UploadedFile.query.filter_by(folder=folder, filename=filename).first()
    if record is not None:
        db.session.delete(record)
