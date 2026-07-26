"""Write ID3/MP4 tags to audio files."""
from __future__ import annotations

from typing import Any

from mutagen import MutagenError
from mutagen.id3 import APIC, COMM, ID3, ID3NoHeaderError, TALB, TBPM, TCON, TIT2, TMOO, TPE1
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover

from toolkit.core.logging import get_logger

logger = get_logger(__name__)


def tag_mp3_file(file_path: str, final_meta: dict[str, Any], write_cover: bool = True) -> bool:
    """Save audio tags to MP3 file."""
    try:
        try:
            audio = MP3(file_path, ID3=ID3)
        except ID3NoHeaderError:
            audio = MP3(file_path)
            audio.add_tags()

        if audio.tags is None:
            audio.add_tags()

        tags = audio.tags
        tags.add(TIT2(encoding=3, text=final_meta["title"]))
        tags.add(TPE1(encoding=3, text=final_meta["artist"]))
        tags.add(TALB(encoding=3, text=final_meta["album"]))
        tags.add(TCON(encoding=3, text=final_meta["genre"]))

        if final_meta["bpm"] > 0:
            tags.add(TBPM(encoding=3, text=str(final_meta["bpm"])))

        tags.add(TMOO(encoding=1, text=final_meta["mood"]))
        tags.add(COMM(encoding=1, lang="eng", desc="", text=f"Mood: {final_meta['mood']}"))

        if write_cover and final_meta["cover_data"]:
            tags.add(
                APIC(
                    encoding=0,
                    mime="image/jpeg",
                    type=3,
                    desc="Cover",
                    data=final_meta["cover_data"],
                )
            )

        audio.save(v2_version=3)
        return True
    except (MutagenError, OSError) as e:
        logger.warning(f"Failed tagging MP3 {file_path}: {e}")
        return False


def tag_m4a_file(file_path: str, final_meta: dict[str, Any], write_cover: bool = True) -> bool:
    """Save audio tags to M4A file."""
    try:
        audio = MP4(file_path)
        audio["\xa9nam"] = final_meta["title"]
        audio["\xa9ART"] = final_meta["artist"]
        audio["\xa9alb"] = final_meta["album"]
        audio["\xa9gen"] = final_meta["genre"]

        if final_meta["year"]:
            audio["\xa9day"] = final_meta["year"]

        if final_meta["bpm"] > 0:
            audio["tmpo"] = [final_meta["bpm"]]

        audio["----:com.apple.iTunes:MOOD"] = final_meta["mood"].encode("utf-8")
        audio["\xa9cmt"] = [f"Mood: {final_meta['mood']}"]

        if write_cover and final_meta["cover_data"]:
            audio["covr"] = [MP4Cover(final_meta["cover_data"], imageformat=MP4Cover.FORMAT_JPEG)]

        audio.save()
        return True
    except (MutagenError, OSError, KeyError, TypeError) as e:
        logger.warning(f"Failed tagging M4A {file_path}: {e}")
        return False
