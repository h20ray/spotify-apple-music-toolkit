"""Embed cover art into MP3/M4A/FLAC files."""
from __future__ import annotations

from mutagen import MutagenError
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, ID3NoHeaderError
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover

from toolkit.core.logging import get_logger

logger = get_logger(__name__)


def embed_artwork_mp3(file_path: str, image_bytes: bytes) -> bool:
    """Embed JPEG/PNG artwork into MP3 ID3 APIC tag."""
    try:
        try:
            audio = MP3(file_path, ID3=ID3)
        except ID3NoHeaderError:
            audio = MP3(file_path)
            audio.add_tags()

        if audio.tags is None:
            audio.add_tags()

        mime = "image/png" if image_bytes.startswith(b"\x89PNG") else "image/jpeg"

        audio.tags.add(
            APIC(
                encoding=0,
                mime=mime,
                type=3,
                desc="Cover",
                data=image_bytes,
            )
        )
        audio.save(v2_version=3)
        return True
    except (MutagenError, OSError) as e:
        logger.warning(f"Failed embedding MP3 art {file_path}: {e}")
        return False


def embed_artwork_m4a(file_path: str, image_bytes: bytes) -> bool:
    """Embed cover art into M4A covr atom tag."""
    try:
        audio = MP4(file_path)
        img_format = MP4Cover.FORMAT_PNG if image_bytes.startswith(b"\x89PNG") else MP4Cover.FORMAT_JPEG
        audio["covr"] = [MP4Cover(image_bytes, imageformat=img_format)]
        audio.save()
        return True
    except (MutagenError, OSError) as e:
        logger.warning(f"Failed embedding M4A art {file_path}: {e}")
        return False


def embed_artwork_flac(file_path: str, image_bytes: bytes) -> bool:
    """Embed cover art into FLAC picture block."""
    try:
        audio = FLAC(file_path)
        picture = Picture()
        picture.type = 3
        picture.mime = "image/png" if image_bytes.startswith(b"\x89PNG") else "image/jpeg"
        picture.desc = "Cover"
        picture.data = image_bytes
        audio.clear_pictures()
        audio.add_picture(picture)
        audio.save()
        return True
    except (MutagenError, OSError) as e:
        logger.warning(f"Failed embedding FLAC art {file_path}: {e}")
        return False


def embed_artwork(file_path: str, image_bytes: bytes) -> bool:
    """Generic wrapper to embed artwork into MP3, M4A, or FLAC."""
    f_lower = file_path.lower()
    if f_lower.endswith(".mp3"):
        return embed_artwork_mp3(file_path, image_bytes)
    if f_lower.endswith(".m4a"):
        return embed_artwork_m4a(file_path, image_bytes)
    if f_lower.endswith(".flac"):
        return embed_artwork_flac(file_path, image_bytes)
    return False
