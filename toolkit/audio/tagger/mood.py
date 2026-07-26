"""Genre-to-mood derivation."""
from __future__ import annotations


def calculate_mood(primary_genre: str = "Pop") -> str:
    """Derive clean text music mood style from genre."""
    genre_lower = primary_genre.lower()
    if any(k in genre_lower for k in ["dance", "edm", "house", "rock", "metal"]):
        return "Energetic"
    if any(k in genre_lower for k in ["indie", "folk", "acoustic", "bedroom", "chill"]):
        return "Chill & Melancholic"
    if any(k in genre_lower for k in ["r&b", "soul", "jazz", "lo-fi", "soft"]):
        return "Smooth & Chill"
    return f"{primary_genre} Style"


