import logging
import os
import uuid
import hashlib
from datetime import datetime

from PIL import Image, ImageOps
from PIL.ExifTags import TAGS

logger = logging.getLogger("photoapp")


def build_filename(original_filename):
    ext = os.path.splitext(original_filename)[1].lower()
    unique_name = str(uuid.uuid4())
    return unique_name + ext


_EXIF_IFD_POINTER = 0x8769  # "ExifOffset" - points at the Exif SubIFD

# Priority order for whichever real metadata date is present. DateTimeOriginal
# (actual capture time) and DateTimeDigitized live in the Exif SubIFD; the
# bare "DateTime" tag on the top-level IFD is only last-modified, but it's
# still real metadata and beats guessing, so it's the final fallback before
# giving up on EXIF entirely.
_TAKEN_DATE_TAGS = ("DateTimeOriginal", "DateTimeDigitized", "DateTime")


def _find_tag_value(tag_dict, wanted_name):
    for tag_id, value in tag_dict.items():
        if TAGS.get(tag_id, tag_id) == wanted_name:
            return value
    return None


def _parse_exif_datetime(value, image_path):
    if value is None:
        return None

    # Some cameras null-pad this field, or write an all-zero placeholder
    # ("0000:00:00 00:00:00") when the date is unknown - neither is a real
    # date.
    value = str(value).strip().rstrip("\x00")

    if not value or value.startswith("0000"):
        return None

    try:
        return datetime.strptime(value, "%Y:%m:%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        logger.warning("Unparseable EXIF date %r for %s", value, image_path)
        return None


def get_photo_taken_date(image_path, fallback):
    """Read the photo's actual capture date from EXIF. `fallback` (the
    upload timestamp, formatted the same way) is used only when the photo
    has no usable date in its metadata at all - callers should pass the
    exact same value they're about to store as the photo's upload_date,
    so the two never drift."""
    try:
        image = Image.open(image_path)
        top_level = image.getexif()

        # DateTimeOriginal/DateTimeDigitized live in the Exif SubIFD, not
        # the top-level IFD that getexif() returns by itself - real camera
        # JPEGs never had these tags at the top level, so scanning only
        # top_level (as this used to) never found them.
        sub_ifd = top_level.get_ifd(_EXIF_IFD_POINTER)

        for tag_name in _TAKEN_DATE_TAGS:
            value = _find_tag_value(sub_ifd, tag_name) or _find_tag_value(top_level, tag_name)
            parsed = _parse_exif_datetime(value, image_path)
            if parsed:
                return parsed

    except Exception:
        logger.exception("Failed to read EXIF date for %s", image_path)

    return fallback


def get_file_hash(file_path):
    sha256 = hashlib.sha256()

    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "/DATA/photoapp/uploads")
PHOTO_FOLDER = os.path.join(UPLOAD_FOLDER, "photos")
FILE_FOLDER = os.path.join(UPLOAD_FOLDER, "files")
THUMBNAIL_FOLDER = os.path.join(UPLOAD_FOLDER, "thumbnails")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PHOTO_FOLDER, exist_ok=True)
os.makedirs(FILE_FOLDER, exist_ok=True)
os.makedirs(THUMBNAIL_FOLDER, exist_ok=True)

THUMBNAIL_SIZE = (400, 400)

MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "500"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

_UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MB


def sanitize_filename(filename: str) -> str:
    """Strip any path component / null bytes so a user-supplied filename
    can never escape the folder it's joined into."""
    name = os.path.basename((filename or "").replace("\x00", ""))

    if not name or name in {".", ".."}:
        raise ValueError("Invalid filename")

    return name


def safe_join(folder: str, filename: str) -> str:
    """os.path.join that refuses to resolve outside `folder`."""
    candidate = os.path.realpath(os.path.join(folder, sanitize_filename(filename)))
    folder_real = os.path.realpath(folder)

    if candidate != folder_real and not candidate.startswith(folder_real + os.sep):
        raise ValueError("Path escapes target folder")

    return candidate


def save_upload(file, dest_path: str, max_bytes: int = MAX_UPLOAD_BYTES) -> int:
    """Stream an UploadFile to disk, aborting (and cleaning up the partial
    file) if it exceeds max_bytes. Returns the number of bytes written."""
    written = 0

    try:
        with open(dest_path, "wb") as buffer:
            while True:
                chunk = file.file.read(_UPLOAD_CHUNK_SIZE)

                if not chunk:
                    break

                written += len(chunk)

                if written > max_bytes:
                    raise ValueError(f"File exceeds the {max_bytes} byte upload limit")

                buffer.write(chunk)
    except ValueError:
        if os.path.exists(dest_path):
            os.remove(dest_path)
        raise

    return written


def is_valid_image(path: str) -> bool:
    try:
        with Image.open(path) as img:
            img.verify()
        return True
    except Exception:
        return False


def make_thumbnail(source_path: str, dest_path: str, size=THUMBNAIL_SIZE) -> None:
    """Generate a resized copy of an image for fast gallery loading.
    Applies the EXIF orientation tag before resizing so rotated phone
    photos come out right-side-up, then saves in the source's own format."""
    with Image.open(source_path) as img:
        fmt = img.format
        # exif_transpose only returns None when called with in_place=True
        # (not the case here) - the `or img` fallback just makes that
        # explicit for the type checker instead of relying on it silently.
        img = ImageOps.exif_transpose(img) or img
        img.thumbnail(size)

        tmp_path = dest_path + ".tmp"
        img.save(tmp_path, format=fmt)
        os.replace(tmp_path, dest_path)


# The BLIP captioning model is large and slow to load, so it's only
# imported/loaded the first time AI tagging is actually needed. This keeps
# app startup fast and lets this module be imported (e.g. in tests) without
# torch/transformers installed at all.
_caption_processor = None
_caption_model = None


def _get_captioner():
    global _caption_processor, _caption_model

    if _caption_processor is None or _caption_model is None:
        from transformers import BlipProcessor, BlipForConditionalGeneration

        _caption_processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
        _caption_model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")

    return _caption_processor, _caption_model


def generate_ai_tags(image_path):
    try:
        processor, model = _get_captioner()

        image = Image.open(image_path).convert("RGB")

        inputs = processor(image, return_tensors="pt")
        output = model.generate(**inputs, max_new_tokens=30)

        caption = processor.decode(output[0], skip_special_tokens=True).lower()

        words_to_remove = {
            "a", "an", "the", "and", "or", "of", "in", "on", "with",
            "is", "are", "there", "this", "that", "photo", "image",
            "picture", "showing", "from", "his", "her", "their", "out",
            "at", "to", "for", "by", "it", "its", "as"
        }

        words = caption.replace(",", "").replace(".", "").split()

        clean_words = []
        for word in words:
            if word not in words_to_remove and len(word) > 2:
                clean_words.append(word)

        tags = set(clean_words)

        clean_caption = " ".join(clean_words)
        if clean_caption:
            tags.add(clean_caption)

        return ", ".join(sorted(tags))

    except Exception:
        logger.exception("AI tagging failed for %s", image_path)
        return ""
