"""
Unified audio metadata reader.
Consolidates duplicate metadata reading logic from tagger, artwork, and lyrics modules.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from mutagen import MutagenError
from mutagen.flac import FLAC
from mutagen.id3 import ID3, ID3NoHeaderError
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

from toolkit.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AudioMetadata:
    """Unified audio metadata structure."""

    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    genre: Optional[str] = None
    year: Optional[str] = None
    bpm: int = 0
    has_cover: bool = False
    file_path: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for backward compatibility."""
        return {
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "genre": self.genre,
            "year": self.year,
            "bpm": self.bpm,
            "has_cover": self.has_cover,
        }


def _read_mp3_metadata(file_path: str) -> AudioMetadata:
    """Read metadata from MP3 file with ID3 tags."""
    meta = AudioMetadata(file_path=file_path)

    try:
        audio = MP3(file_path, ID3=ID3)
        if not audio.tags:
            return meta

        tags = audio.tags

        # Title
        if "TIT2" in tags and tags["TIT2"].text:
            meta.title = str(tags["TIT2"].text[0]).strip()

        # Artist
        if "TPE1" in tags and tags["TPE1"].text:
            meta.artist = str(tags["TPE1"].text[0]).strip()

        # Album
        if "TALB" in tags and tags["TALB"].text:
            meta.album = str(tags["TALB"].text[0]).strip()

        # Genre
        if "TCON" in tags and tags["TCON"].text:
            meta.genre = str(tags["TCON"].text[0]).strip()

        # Year (TDRC for ID3v2.4, TYER for ID3v2.3)
        if "TDRC" in tags and tags["TDRC"].text:
            meta.year = str(tags["TDRC"].text[0]).strip()[:4]
        elif "TYER" in tags and tags["TYER"].text:
            meta.year = str(tags["TYER"].text[0]).strip()[:4]

        # BPM
        if "TBPM" in tags and tags["TBPM"].text:
            try:
                meta.bpm = int(round(float(str(tags["TBPM"].text[0]).strip())))
            except (ValueError, IndexError) as e:
                logger.debug(f"Failed to parse BPM from {file_path}: {e}")

        # Cover art
        meta.has_cover = any(k.startswith("APIC") for k in tags.keys())

    except ID3NoHeaderError:
        logger.debug(f"No ID3 header in {file_path}")
    except MutagenError as e:
        logger.warning(f"Failed to read MP3 metadata from {file_path}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error reading MP3 {file_path}: {e}")

    return meta


def _read_m4a_metadata(file_path: str) -> AudioMetadata:
    """Read metadata from M4A/MP4 file."""
    meta = AudioMetadata(file_path=file_path)

    try:
        audio = MP4(file_path)

        # Title
        if "©nam" in audio and audio["©nam"]:
            meta.title = str(audio["©nam"][0]).strip()

        # Artist
        if "©ART" in audio and audio["©ART"]:
            meta.artist = str(audio["©ART"][0]).strip()

        # Album
        if "©alb" in audio and audio["©alb"]:
            meta.album = str(audio["©alb"][0]).strip()

        # Genre
        if "©gen" in audio and audio["©gen"]:
            meta.genre = str(audio["©gen"][0]).strip()

        # Year
        if "©day" in audio and audio["©day"]:
            meta.year = str(audio["©day"][0]).strip()[:4]

        # BPM
        if "tmpo" in audio and audio["tmpo"]:
            try:
                meta.bpm = int(audio["tmpo"][0])
            except (ValueError, IndexError, TypeError) as e:
                logger.debug(f"Failed to parse BPM from {file_path}: {e}")

        # Cover art
        meta.has_cover = "covr" in audio and bool(audio["covr"])

    except MutagenError as e:
        logger.warning(f"Failed to read M4A metadata from {file_path}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error reading M4A {file_path}: {e}")

    return meta


def _read_flac_metadata(file_path: str) -> AudioMetadata:
    """Read metadata from FLAC file."""
    meta = AudioMetadata(file_path=file_path)

    try:
        audio = FLAC(file_path)

        # Title
        if "title" in audio and audio["title"]:
            meta.title = str(audio["title"][0]).strip()

        # Artist
        if "artist" in audio and audio["artist"]:
            meta.artist = str(audio["artist"][0]).strip()

        # Album
        if "album" in audio and audio["album"]:
            meta.album = str(audio["album"][0]).strip()

        # Genre
        if "genre" in audio and audio["genre"]:
            meta.genre = str(audio["genre"][0]).strip()

        # Year
        if "date" in audio and audio["date"]:
            meta.year = str(audio["date"][0]).strip()[:4]

        # BPM
        if "bpm" in audio and audio["bpm"]:
            try:
                meta.bpm = int(audio["bpm"][0])
            except (ValueError, IndexError, TypeError) as e:
                logger.debug(f"Failed to parse BPM from {file_path}: {e}")

        # Cover art
        meta.has_cover = bool(audio.pictures)

    except MutagenError as e:
        logger.warning(f"Failed to read FLAC metadata from {file_path}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error reading FLAC {file_path}: {e}")

    return meta


def read_audio_metadata(file_path: str) -> AudioMetadata:
    """
    Read metadata from audio file (MP3, M4A, or FLAC).

    Args:
        file_path: Path to audio file

    Returns:
        AudioMetadata object with all available metadata

    Example:
        >>> meta = read_audio_metadata("song.mp3")
        >>> print(meta.title, meta.artist)
    """
    if not os.path.exists(file_path):
        logger.warning(f"File not found: {file_path}")
        return AudioMetadata(file_path=file_path)

    file_lower = file_path.lower()

    if file_lower.endswith(".mp3"):
        return _read_mp3_metadata(file_path)
    elif file_lower.endswith(".m4a"):
        return _read_m4a_metadata(file_path)
    elif file_lower.endswith(".flac"):
        return _read_flac_metadata(file_path)
    else:
        logger.debug(f"Unsupported audio format: {file_path}")
        return AudioMetadata(file_path=file_path)


# ============================================================================
# Backward Compatibility Wrappers
# ============================================================================


def read_all_existing_metadata(file_path: str) -> dict:
    """
    Backward compatibility wrapper for tagger.py.
    Returns dict format instead of AudioMetadata.
    """
    return read_audio_metadata(file_path).to_dict()


def read_audio_tags(file_path: str) -> dict:
    """
    Backward compatibility wrapper for artwork.py.
    Returns dict with subset of fields (title, artist, album, has_cover).
    """
    meta = read_audio_metadata(file_path)
    return {
        "title": meta.title,
        "artist": meta.artist,
        "album": meta.album,
        "has_cover": meta.has_cover,
    }


def read_local_audio_metadata(file_path: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Backward compatibility wrapper for lyrics.py.
    Returns tuple (title, artist, album).
    """
    meta = read_audio_metadata(file_path)
    return meta.title, meta.artist, meta.album
