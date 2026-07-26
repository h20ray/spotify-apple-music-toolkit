"""Physical BPM detection via librosa."""
from __future__ import annotations

from toolkit.core.constants import LIBROSA_DURATION_SECONDS
from toolkit.core.logging import get_logger

logger = get_logger(__name__)


def detect_physical_bpm(file_path: str) -> int:
    """Calculate exact physical song tempo (BPM) from audio signal."""
    try:
        import librosa

        y, sr = librosa.load(file_path, duration=LIBROSA_DURATION_SECONDS)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        return int(round(float(tempo[0] if hasattr(tempo, "__len__") else tempo)))
    except Exception as e:
        logger.warning(f"BPM detection failed for {file_path}: {e}")
        return 0


