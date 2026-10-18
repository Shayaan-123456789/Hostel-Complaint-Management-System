"""Private image upload and download; no public Django /media/ route."""
import io
import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from PIL import Image, UnidentifiedImageError

from .security import ApiError

ALLOWED = {'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp'}


def save_photo(upload):
    if upload is None:
        return None
    if upload.size == 0 or upload.size > settings.HOSTEL_MAX_UPLOAD_MB * 1024 * 1024:
        raise ApiError(f'Photo must be between 1 byte and {settings.HOSTEL_MAX_UPLOAD_MB} MB.')
    try:
        # Read capped bytes, validate actual image content rather than extension.
        raw = upload.read(settings.HOSTEL_MAX_UPLOAD_MB * 1024 * 1024 + 1)
        if len(raw) > settings.HOSTEL_MAX_UPLOAD_MB * 1024 * 1024:
            raise ApiError('Photo is too large.')
        with Image.open(io.BytesIO(raw)) as img:
            image_format = img.format
            img.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ApiError('Upload a valid JPEG, PNG, or WebP image.') from exc
    if image_format not in ALLOWED:
        raise ApiError('Only JPEG, PNG, and WebP images are accepted.')
    filename = f'complaints/{uuid.uuid4().hex}{ALLOWED[image_format]}'
    storage = FileSystemStorage(location=settings.MEDIA_ROOT)
    return storage.save(filename, io.BytesIO(raw))


def delete_photo(path):
    if path:
        FileSystemStorage(location=settings.MEDIA_ROOT).delete(path)


def private_photo_path(path):
    if not isinstance(path, str) or not path.startswith('complaints/'):
        raise ApiError('This photo is not available on the private media store.', 404)
    base = Path(settings.MEDIA_ROOT).resolve()
    full = (base / path).resolve()
    if not full.is_relative_to(base) or not full.is_file():
        raise ApiError('Photo file not found.', 404)
    return full
