"""
Playlist Parser & Sanitizer Module.
Provides shared helper routines to read, clean, sanitize, and parse text song lists,
generate search queries, and strictly verify artist/title candidate matches.
Dynamically loads keyword filters from user-editable config/keywords.json.
"""

import os
import re
import unicodedata
from toolkit.core import (
    PLAYLIST_SOURCES_DIR,
    SOURCE_TEXT_FILES_DIR,
    ensure_all_folders,
    load_keywords_config,
)

# Dynamically load keyword sets from config/keywords.json
_KW_CONFIG = load_keywords_config()
COMPILATION_KEYWORDS = _KW_CONFIG.get("compilations", [])
KARAOKE_TRIBUTE_KEYWORDS = _KW_CONFIG.get("karaoke_and_tributes", [])
UNWANTED_VERSION_KEYWORDS = _KW_CONFIG.get("unwanted_versions", [])
UNWANTED_EDIT_KEYWORDS = _KW_CONFIG.get("unwanted_edits", [])

def refresh_keywords():
    """Reload keywords from config/keywords.json at runtime if modified."""
    global _KW_CONFIG, COMPILATION_KEYWORDS, KARAOKE_TRIBUTE_KEYWORDS, UNWANTED_VERSION_KEYWORDS, UNWANTED_EDIT_KEYWORDS
    _KW_CONFIG = load_keywords_config()
    COMPILATION_KEYWORDS = _KW_CONFIG.get("compilations", [])
    KARAOKE_TRIBUTE_KEYWORDS = _KW_CONFIG.get("karaoke_and_tributes", [])
    UNWANTED_VERSION_KEYWORDS = _KW_CONFIG.get("unwanted_versions", [])
    UNWANTED_EDIT_KEYWORDS = _KW_CONFIG.get("unwanted_edits", [])

def parse_songs(file_path):
    """Parse track titles from text file."""
    if not os.path.exists(file_path):
        return []
    songs = []
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            cleaned = line.strip()
            if cleaned and not cleaned.startswith("==="):
                songs.append(cleaned)
    return songs

def clean_string(text):
    """Normalize string for comparison, stripping accents and expanding explicit censorship masks."""
    if not text:
        return ""
    text = text.lower()
    # Normalize Greek Lambda symbol (Axwell Λ Ingrosso -> Axwell a Ingrosso)
    text = text.replace('λ', 'a').replace('Λ', 'a')
    # Strip unicode accents/diacritics (e.g. Beyoncé -> Beyonce)
    text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    # Normalize explicit censorship asterisks (e.g. f*ck, f**k, f***ing, b*ch, s*t)
    text = re.sub(r'\bf[\*\.\_]+c?k\b', 'fuck', text)
    text = re.sub(r'\bf[\*\.\_]+c?king\b', 'fucking', text)
    text = re.sub(r'\bb[\*\.\_]+t?ch\b', 'bitch', text)
    text = re.sub(r'\bs[\*\.\_]+h?t\b', 'shit', text)
    text = re.sub(r'\ba[\*\.\_]+s?s?hole\b', 'asshole', text)
    # Remove remaining punctuation
    text = re.sub(r'[\(\)\[\]\{\}\-\_\,\.\:\;\"\'\!\?\/\\]', ' ', text)
    return ' '.join(text.split())

def pre_sanitize_song_line(line):
    """Pre-sanitize raw playlist text line (strip track numbers, video tags, extra spaces)."""
    if not line:
        return ""
    # Strip leading track numbers like '01. ', '1 - ', '[01] ', '01) '
    l = re.sub(r'^\s*\[?\d+\]?[\.\-\)]\s*', '', line.strip())
    # Strip video/audio tags like [Official Audio], (Official Video), (Lyrics), (Audio), (Visualizer)
    l = re.sub(r'[\(\[\{]\s*(?:Official|Audio|Video|Lyrics|Visualizer|HD|4K|Topic).+?[\)\]\}]', '', l, flags=re.IGNORECASE)
    # Strip leading/trailing quotes and normalize spacing
    l = l.strip('"\' ')
    return re.sub(r'\s+', ' ', l).strip()

def extract_artist_title(song_line):
    """Extract (artist, title) tuple from song line if ' - ' delimiter is present, else (None, title)."""
    clean_line = pre_sanitize_song_line(song_line)
    if ' - ' in clean_line:
        parts = clean_line.split(' - ', 1)
        return parts[0].strip(), parts[1].strip()
    return None, clean_line

def verify_title_match(target_title, candidate_title):
    """
    Strictly verifies if candidate track title matches expected target title.
    Prevents false matches where artist matches but candidate song title is completely different
    (e.g., target 'Cahaya Bulan' vs candidate 'Huboan Pe Ho Tu Bulan').
    """
    if not target_title or not candidate_title:
        return False

    t_clean = clean_string(target_title)
    c_clean = clean_string(candidate_title)

    if not t_clean or not c_clean:
        return False

    # Direct substring or exact match
    if t_clean in c_clean or c_clean in t_clean:
        return True

    # Strip common parenthetical tags like (live), (remix), [official video]
    t_core = re.sub(r'[\(\[\{].*?[\)\]\}]', '', t_clean).strip()
    c_core = re.sub(r'[\(\[\{].*?[\)\]\}]', '', c_clean).strip()

    if t_core in c_core or c_core in t_core:
        return True

    stopwords = {'a', 'an', 'the', 'and', 'or', 'of', 'in', 'on', 'at', 'to', 'for', 'with', 'by'}
    t_words = [w for w in t_core.split() if w not in stopwords and len(w) >= 2]
    c_words = [w for w in c_core.split() if w not in stopwords and len(w) >= 2]

    if not t_words:
        return True

    matched_count = 0
    for tw in t_words:
        if any(tw == cw or (len(tw) >= 4 and (tw in cw or cw in tw)) for cw in c_words):
            matched_count += 1

    ratio = matched_count / len(t_words)

    # Strict rule:
    # For titles with 1 or 2 core words, ALL core words must match unless target title is long (3+ words) where 65%+ match is allowed.
    if len(t_words) <= 2:
        return matched_count == len(t_words)
    else:
        return ratio >= 0.65

def verify_artist_match(target_artist, candidate_artist):
    """
    Strictly verifies candidate artist against target artist with spacing normalization and word boundary checks.
    Allows '5 Romeo' to match '5Romeo', while rejecting 'A.B.A. Three' vs 'AB Three'.
    """
    if not target_artist or not candidate_artist:
        return True

    ta_clean = clean_string(target_artist)
    ca_clean = clean_string(candidate_artist)

    if not ta_clean or not ca_clean:
        return True

    if ta_clean in ca_clean or ca_clean in ta_clean:
        return True

    ta_primary = re.split(r'\s*(?:&|,|/|\\|\bfeat\.\b|\bft\.\b|\bfeaturing\b|\bwith\b|\bvs\.\b|\bvs\b|\bx\b)\s*', ta_clean)[0].strip()
    ca_primary = re.split(r'\s*(?:&|,|/|\\|\bfeat\.\b|\bft\.\b|\bfeaturing\b|\bwith\b|\bvs\.\b|\bvs\b|\bx\b)\s*', ca_clean)[0].strip()

    if ta_primary == ca_primary:
        return True

    # Compact spacing check for number-artist and fused name variations (e.g., '5 Romeo' <-> '5Romeo')
    ta_compact = ''.join(ta_primary.split()).replace('.', '')
    ca_compact = ''.join(ca_primary.split()).replace('.', '')

    if ta_compact == ca_compact:
        return True
    if len(ta_compact) >= 4 and (ta_compact in ca_compact or ca_compact in ta_compact):
        return True

    ta_words = [w for w in ta_primary.split() if len(w) >= 2]
    ca_words = [w for w in ca_primary.split() if len(w) >= 2]

    if not ta_words or not ca_words:
        return True

    # Word boundary check
    for tw in ta_words:
        if tw not in ca_words and not any(tw in cw for cw in ca_words):
            return False

    return True

def verify_track_match(song_line, candidate_title, candidate_artist=None):
    """
    Verify if candidate track title & artist strictly match target song line.
    """
    clean_line = pre_sanitize_song_line(song_line)
    if ' - ' in clean_line:
        parts = clean_line.split(' - ', 1)
        p1, p2 = parts[0].strip(), parts[1].strip()

        # Scenario A: p1 is artist, p2 is title
        art_match_a = verify_artist_match(p1, candidate_artist) if candidate_artist else True
        title_match_a = verify_title_match(p2, candidate_title)
        if art_match_a and title_match_a:
            return True

        # Scenario B: p2 is artist, p1 is title
        art_match_b = verify_artist_match(p2, candidate_artist) if candidate_artist else True
        title_match_b = verify_title_match(p1, candidate_title)
        if art_match_b and title_match_b:
            return True

        return False
    else:
        return verify_title_match(clean_line, candidate_title)

def generate_search_queries(song_line):
    """Smart parser to generate clean search queries for both Artist-Title and Title-Artist formats."""
    clean_line = pre_sanitize_song_line(song_line)
    queries = [clean_line]

    # Spacing normalization for digits (e.g. 5 Romeo -> 5Romeo)
    num_word_var = re.sub(r'(\b\d+)\s+([a-zA-Z]+)', r'\1\2', clean_line)
    if num_word_var != clean_line:
        queries.append(num_word_var)

    # Ampersand vs 'and' variation (e.g. The Trees and The Wild <-> The Trees & The Wild)
    if " and " in clean_line.lower():
        queries.append(re.sub(r'\band\b', '&', clean_line, flags=re.IGNORECASE).strip())
    if " & " in clean_line:
        queries.append(re.sub(r'&', 'and', clean_line, flags=re.IGNORECASE).strip())

    # Explicit censorship search variation (e.g. fuck -> f**k, fucking -> f***ing)
    censored_line = clean_line
    censored_line = re.sub(r'\bfuck\b', 'f**k', censored_line, flags=re.IGNORECASE)
    censored_line = re.sub(r'\bfucking\b', 'f***ing', censored_line, flags=re.IGNORECASE)
    censored_line = re.sub(r'\bbitch\b', 'b**ch', censored_line, flags=re.IGNORECASE)
    censored_line = re.sub(r'\bshit\b', 's**t', censored_line, flags=re.IGNORECASE)
    if censored_line != clean_line:
        queries.append(censored_line)

    if ' - ' in clean_line:
        parts = clean_line.split(' - ', 1)
        p1, p2 = parts[0].strip(), parts[1].strip()

        p1_clean = re.sub(r'[\(\[\{].*?[\)\]\}]', '', p1).strip()
        p1_clean = re.sub(r'[\(\[\{].*$', '', p1_clean).strip()
        p2_clean = re.sub(r'[\(\[\{].*?[\)\]\}]', '', p2).strip()
        p2_clean = re.sub(r'[\(\[\{].*$', '', p2_clean).strip()

        queries.append(f"{p1_clean} {p2_clean}".strip())
        queries.append(f"{p2_clean} {p1_clean}".strip())

        p1_primary = re.split(r'\s*(?:&|,|/|\\|\bfeat\.\b|\bft\.\b|\bfeaturing\b|\bwith\b|\bvs\.\b|\bvs\b|\bx\b)\s*', p1_clean, flags=re.IGNORECASE)[0].strip()
        p2_primary = re.split(r'\s*(?:&|,|/|\\|\bfeat\.\b|\bft\.\b|\bfeaturing\b|\bwith\b|\bvs\.\b|\bvs\b|\bx\b)\s*', p2_clean, flags=re.IGNORECASE)[0].strip()

        queries.append(f"{p1_primary} {p2_clean}".strip())
        queries.append(f"{p2_primary} {p1_clean}".strip())

        # Unspaced artist variation for p1
        p1_unspaced = re.sub(r'(\b\d+)\s+([a-zA-Z]+)', r'\1\2', p1_primary)
        if p1_unspaced != p1_primary:
            queries.append(f"{p1_unspaced} {p2_clean}".strip())

        for tw in p2_clean.split():
            if len(tw) >= 4 and not tw.endswith("ing"):
                ing_var = tw[:-1] + "ing" if tw.endswith("e") else tw + "ing"
                queries.append(f"{p1_primary} {ing_var}".strip())

        if censored_line != clean_line:
            p2_censored = re.sub(r'\bfuck\b', 'f**k', p2_clean, flags=re.IGNORECASE)
            p2_censored = re.sub(r'\bfucking\b', 'f***ing', p2_censored, flags=re.IGNORECASE)
            queries.append(f"{p1_primary} {p2_censored}".strip())
    else:
        c_line = re.sub(r'[\(\[\{].*?[\)\]\}]', '', clean_line).strip()
        queries.append(c_line)

    seen = set()
    dedup_queries = []
    for q in queries:
        if q and q.lower() not in seen:
            seen.add(q.lower())
            dedup_queries.append(q)

    return dedup_queries

def scan_playlist_files():
    """Scan playlist text files in source_text_files or fallback directory."""
    ensure_all_folders()

    txt_candidates = []
    seen_names = set()

    # Priority 1: source_text_files
    if os.path.exists(SOURCE_TEXT_FILES_DIR):
        for f in sorted(os.listdir(SOURCE_TEXT_FILES_DIR)):
            if f.lower().endswith('.txt') and not f.lower().endswith('_report.txt'):
                txt_candidates.append(os.path.join(SOURCE_TEXT_FILES_DIR, f))
                seen_names.add(f)

    # Priority 2: playlist_sources fallback
    if os.path.exists(PLAYLIST_SOURCES_DIR):
        for f in sorted(os.listdir(PLAYLIST_SOURCES_DIR)):
            if f.lower().endswith('.txt') and not f.lower().endswith('_report.txt') and f not in seen_names:
                fpath = os.path.join(PLAYLIST_SOURCES_DIR, f)
                if os.path.isfile(fpath):
                    txt_candidates.append(fpath)

    file_info_list = []
    for full_path in txt_candidates:
        filename = os.path.basename(full_path)
        song_count = 0
        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                c = line.strip()
                if c and not c.startswith("==="):
                    song_count += 1
        size_bytes = os.path.getsize(full_path)
        file_info_list.append({
            'filename': filename,
            'path': full_path,
            'song_count': song_count,
            'size': size_bytes
        })
    return file_info_list
