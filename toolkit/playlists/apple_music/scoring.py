"""Apple Music track candidate scoring."""
from __future__ import annotations

import re

from toolkit.core.constants import (
    APPLE_BONUS_ARTIST_TITLE_MATCH,
    APPLE_BONUS_EXACT_TITLE,
    APPLE_BONUS_TITLE_MATCH,
    APPLE_PENALTY_ACOUSTIC,
    APPLE_PENALTY_COMPILATION,
    APPLE_PENALTY_KARAOKE,
    APPLE_PENALTY_LIVE,
    APPLE_PENALTY_NO_ARTIST,
    APPLE_PENALTY_REMIX,
    APPLE_PENALTY_UNWANTED_VERSION,
    APPLE_SCORE_GOOD,
    APPLE_SCORE_MISMATCH,
)
from toolkit.playlists.parser import (
    COMPILATION_KEYWORDS,
    KARAOKE_TRIBUTE_KEYWORDS,
    UNWANTED_EDIT_KEYWORDS,
    UNWANTED_VERSION_KEYWORDS,
    clean_string,
    verify_track_match,
)


def score_track_candidate(item, song_line, user_wants_remix, user_wants_live):
    """
    Score candidate track against query string with title/artist match verification.
    """
    attr = item.get('attributes', {})
    track_name = attr.get('name') or item.get('trackName') or ''
    artist_name = attr.get('artistName') or item.get('artistName') or ''
    album_name = attr.get('albumName') or item.get('collectionName') or ''

    # Strict artist & title disambiguation check (disqualifies mismatched songs like AB Three vs A.B.A. Three)
    if not verify_track_match(song_line, track_name, artist_name):
        return APPLE_SCORE_MISMATCH

    tn_clean = clean_string(track_name)
    an_clean = clean_string(artist_name)
    album_clean = clean_string(album_name)

    query_clean = clean_string(song_line)
    words = [w for w in query_clean.split() if len(w) > 1]

    score = 0.0
    matched_words = 0.0

    full_all_words = (tn_clean + " " + an_clean + " " + album_clean).split()
    for w in words:
        if w in tn_clean or w in an_clean or w in album_clean:
            matched_words += 1.0
        elif len(w) >= 4:
            w_stem = w[:4]
            if any(tw.startswith(w_stem) or w_stem in tw for tw in full_all_words if len(tw) >= 4):
                matched_words += 0.9

    if words:
        score += (matched_words / len(words)) * APPLE_SCORE_GOOD

    if " - " in song_line:
        parts = song_line.split(" - ", 1)
        p1_c = clean_string(parts[0])
        p2_c = clean_string(parts[1])

        p1_primary = clean_string(
            re.split(
                r"\s*(?:&|,|/|\\|\bfeat\.\b|\bft\.\b|\bfeaturing\b|\bwith\b|\bvs\.\b|\bvs\b|\bx\b)\s*",
                parts[0],
                flags=re.IGNORECASE,
            )[0]
        )
        p2_primary = clean_string(
            re.split(
                r"\s*(?:&|,|/|\\|\bfeat\.\b|\bft\.\b|\bfeaturing\b|\bwith\b|\bvs\.\b|\bvs\b|\bx\b)\s*",
                parts[1],
                flags=re.IGNORECASE,
            )[0]
        )

        p1_no_the = re.sub(r"^\bthe\b\s*", "", p1_c) if p1_c else ""
        p2_no_the = re.sub(r"^\bthe\b\s*", "", p2_c) if p2_c else ""
        an_no_the = re.sub(r"^\bthe\b\s*", "", an_clean) if an_clean else ""

        p1_primary_no_the = re.sub(r"^\bthe\b\s*", "", p1_primary) if p1_primary else ""
        p2_primary_no_the = re.sub(r"^\bthe\b\s*", "", p2_primary) if p2_primary else ""

        p1_words = [w for w in p1_c.split() if len(w) >= 3]
        p2_words = [w for w in p2_c.split() if len(w) >= 3]

        p1_all_words_in_art = bool(p1_words and all(w in an_clean or w in an_no_the for w in p1_words))
        p2_all_words_in_art = bool(p2_words and all(w in an_clean or w in an_no_the for w in p2_words))

        p1_in_art = (
            bool(p1_c and p1_c in an_clean)
            or bool(p1_no_the and p1_no_the in an_no_the)
            or p1_all_words_in_art
            or bool(an_clean and len(an_clean) >= 3 and (an_clean in p1_c or an_no_the in p1_no_the))
            or bool(p1_primary and len(p1_primary) >= 3 and (p1_primary in an_clean or p1_primary_no_the in an_no_the))
        )

        p2_in_art = (
            bool(p2_c and p2_c in an_clean)
            or bool(p2_no_the and p2_no_the in an_no_the)
            or p2_all_words_in_art
            or bool(an_clean and len(an_clean) >= 3 and (an_clean in p2_c or an_no_the in p2_no_the))
            or bool(p2_primary and len(p2_primary) >= 3 and (p2_primary in an_clean or p2_primary_no_the in an_no_the))
        )

        p1_in_title = bool(p1_c and (p1_c in tn_clean or tn_clean in p1_c))
        p2_in_title = bool(p2_c and (p2_c in tn_clean or tn_clean in p2_c))

        if not p2_in_title and p2_c and len(p2_c) >= 4:
            p2_stem = p2_c[:4]
            if any(tw.startswith(p2_stem) for tw in tn_clean.split() if len(tw) >= 4):
                p2_in_title = True

        if (p1_in_art and p2_in_title) or (p2_in_art and p1_in_title):
            score += APPLE_BONUS_ARTIST_TITLE_MATCH
        elif p1_in_title or p2_in_title:
            score += APPLE_BONUS_TITLE_MATCH

        if (p1_in_art and p2_c and tn_clean == p2_c) or (p2_in_art and p1_c and tn_clean == p1_c):
            score += APPLE_BONUS_EXACT_TITLE

        if not p1_in_art and not p2_in_art:
            score += APPLE_PENALTY_NO_ARTIST

    full_candidate_all = f"{tn_clean} {an_clean} {album_clean}"

    sl = song_line.lower()
    user_wants_karaoke = "karaoke" in sl or "tribute" in sl or "cover" in sl
    if not user_wants_karaoke:
        for kw in KARAOKE_TRIBUTE_KEYWORDS:
            if kw in full_candidate_all:
                score += APPLE_PENALTY_KARAOKE
                break

    full_candidate_text = f"{tn_clean} {album_clean}"

    if not user_wants_remix:
        for kw in UNWANTED_EDIT_KEYWORDS:
            if kw in full_candidate_text:
                score += APPLE_PENALTY_REMIX
                break

    if not user_wants_live:
        for kw in ["live", "live at", "in concert", "live in"]:
            if kw in full_candidate_text:
                score += APPLE_PENALTY_LIVE
                break

    user_wants_acoustic = "acoustic" in song_line.lower()
    if not user_wants_acoustic and "acoustic" in full_candidate_text:
        score += APPLE_PENALTY_ACOUSTIC

    for kw in UNWANTED_VERSION_KEYWORDS:
        if kw in ["live", "acoustic", "instrumental"] and (user_wants_live or user_wants_remix or user_wants_acoustic):
            continue
        if kw in full_candidate_text:
            score += APPLE_PENALTY_UNWANTED_VERSION

    for c_kw in COMPILATION_KEYWORDS:
        if c_kw in album_clean:
            score += APPLE_PENALTY_COMPILATION
            break

    return score
