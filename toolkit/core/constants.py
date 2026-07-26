"""
Centralized constants for Spotify-Apple Music Toolkit.
Eliminates magic numbers and strings scattered across modules.
"""

from __future__ import annotations

# ============================================================================
# Threading & Performance
# ============================================================================

DEFAULT_MAX_WORKERS = 10
MAX_WORKERS_MIN = 1
MAX_WORKERS_MAX = 50

# ============================================================================
# API Timeouts (seconds)
# ============================================================================

TIMEOUT_API_SHORT = 6
TIMEOUT_API_MEDIUM = 8
TIMEOUT_API_LONG = 10
TIMEOUT_IMAGE_DOWNLOAD = 8

# ============================================================================
# Apple Music Scoring Thresholds
# ============================================================================

# Score thresholds for track matching confidence
APPLE_SCORE_EXCELLENT = 75.0  # High confidence match, early exit
APPLE_SCORE_GOOD = 60.0  # Good match, acceptable
APPLE_SCORE_MINIMUM = 15.0  # Minimum threshold to accept
APPLE_SCORE_MISMATCH = -500.0  # Disqualified (artist/title mismatch)

# Score penalties
APPLE_PENALTY_KARAOKE = -100.0
APPLE_PENALTY_NO_ARTIST = -80.0
APPLE_PENALTY_REMIX = -40.0
APPLE_PENALTY_LIVE = -50.0
APPLE_PENALTY_ACOUSTIC = -50.0
APPLE_PENALTY_UNWANTED_VERSION = -30.0
APPLE_PENALTY_COMPILATION = -15.0

# Score bonuses
APPLE_BONUS_ARTIST_TITLE_MATCH = 40.0
APPLE_BONUS_TITLE_MATCH = 20.0
APPLE_BONUS_EXACT_TITLE = 20.0

# ============================================================================
# Album Quality Scores (Artwork)
# ============================================================================

QUALITY_SCORE_COMPILATION = 5
QUALITY_SCORE_STANDARD = 10
QUALITY_SCORE_SINGLE_EP = 70
QUALITY_SCORE_DELUXE_REMASTER = 80
QUALITY_SCORE_STUDIO_ALBUM = 100

# ============================================================================
# User-Agent Strings
# ============================================================================

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "iTunes/12.12.0 (Windows; Microsoft Windows 10 x64)",
    "AppleMusic/1.0 (Macintosh; Intel Mac OS X 10_15_7)",
]

DEFAULT_USER_AGENT = USER_AGENTS[0]

# ============================================================================
# File Size Thresholds
# ============================================================================

MIN_IMAGE_SIZE_BYTES = 5000  # Minimum valid image file size

# ============================================================================
# Cache & Rate Limiting
# ============================================================================

CACHE_SAVE_INTERVAL = 5  # Save cache every N tracks
RATE_LIMIT_DELAY = 0.1  # Delay between API requests (seconds)
RATE_LIMIT_BACKOFF_MULTIPLIER = 1.5  # Exponential backoff for 429 responses
MAX_RETRY_ATTEMPTS = 4  # Maximum retry attempts for failed requests

# ============================================================================
# Apple Music API
# ============================================================================

APPLE_MUSIC_API_CHUNK_SIZE = 20  # Tracks per batch when adding to playlist
APPLE_MUSIC_API_RETRY_DELAY = 2.0  # Base delay for retries (seconds)

# ============================================================================
# iTunes Artwork
# ============================================================================

ITUNES_ARTWORK_HIGH_RES = "1000x1000bb"
ITUNES_ARTWORK_FALLBACK_SIZES = ["800x800bb", "600x600bb"]

# ============================================================================
# Audio Processing
# ============================================================================

LIBROSA_DURATION_SECONDS = 30  # Duration for BPM analysis
LIBROSA_SAMPLE_RATE = 22050  # Default sample rate

# ============================================================================
# Playlist Export
# ============================================================================

SPOTIFY_PLAYLIST_BATCH_SIZE = 100  # Tracks per batch when adding to playlist

# ============================================================================
# Validation
# ============================================================================

MIN_TITLE_LENGTH = 2  # Minimum title length for validation
MIN_ARTIST_LENGTH = 2  # Minimum artist length for validation
WORD_MATCH_THRESHOLD = 0.65  # 65% word match for title verification
