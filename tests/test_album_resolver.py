"""Tests for original-album resolution (iTunes + MusicBrainz) and the album fixer decision logic."""

from toolkit.audio.album_fixer import (
    STATUS_CHANGE,
    STATUS_NOT_FOUND,
    STATUS_OK,
    STATUS_REVIEW,
    decide,
    shared_album_names,
)
from toolkit.audio.album_resolver import (
    choose_itunes,
    choose_musicbrainz,
    is_compilation_name,
    strip_edition,
)
from toolkit.audio.artwork import score_album_quality
from toolkit.core.constants import QUALITY_SCORE_STUDIO_ALBUM


def _item(track, album, date, artist="Green Day", **extra):
    return {"trackName": track, "artistName": artist, "collectionName": album, "releaseDate": date + "-01-01", **extra}


def test_is_compilation_name():
    assert is_compilation_name("Millennium Pop Hits")
    assert is_compilation_name("Funeral Songs: In Memoriam")
    assert is_compilation_name("2001 Best of by uDiscover")
    assert not is_compilation_name("Dookie")
    assert is_compilation_name("The Essential 311", "311")  # best-of by the same artist is still a compilation
    assert not is_compilation_name("311", "311")


def test_score_album_quality_ep_substring_bug():
    assert score_album_quality("Sleep Through the Static", "Jack Johnson") == QUALITY_SCORE_STUDIO_ALBUM
    assert score_album_quality("Deep", "Artist") == QUALITY_SCORE_STUDIO_ALBUM


def test_choose_itunes_prefers_studio_over_compilation_and_live():
    results = [
        _item("Basket Case", "Rock from the 90s", "1994", collectionArtistName="Various Artists"),
        _item("Basket Case (Live)", "Bullet In a Bible", "2005"),
        _item("Basket Case", "International Superhits!", "2001"),
        _item("Basket Case", "Dookie", "1994"),
    ]
    best = choose_itunes(results, "Green Day", "Basket Case", "1994")
    assert best["album"] == "Dookie"
    assert best["score"] >= 70


def test_choose_itunes_only_live_scores_below_threshold():
    results = [_item("Good Riddance (Time of Your Life) [Live]", "Awesome As Fuck (Live)", "2011")]
    best = choose_itunes(results, "Green Day", "Good Riddance (Time of Your Life)", "1997")
    assert best["score"] < 70


def test_choose_itunes_ignores_other_songs_and_artists():
    results = [_item("Other Song", "Dookie", "1994"), _item("Basket Case", "Dookie", "1994", artist="Someone Else")]
    assert choose_itunes(results, "Green Day", "Basket Case") is None


def test_choose_musicbrainz_earliest_plain_album():
    recordings = [
        {
            "releases": [
                {
                    "title": "Greatest Hits",
                    "status": "Official",
                    "date": "2010-01-01",
                    "release-group": {"id": "g1", "primary-type": "Album", "secondary-types": ["Compilation"]},
                },
                {
                    "title": "nimrod.",
                    "status": "Official",
                    "date": "1997-10-14",
                    "release-group": {"id": "g2", "primary-type": "Album", "secondary-types": []},
                },
                {
                    "title": "nimrod. (bootleg)",
                    "status": "Bootleg",
                    "date": "1990-01-01",
                    "release-group": {"id": "g3", "primary-type": "Album", "secondary-types": []},
                },
            ]
        }
    ]
    best = choose_musicbrainz(recordings)
    assert best["album"] == "nimrod."
    assert best["year"] == "1997"
    assert best["art_url"].endswith("g2/front-1200")


def test_strip_edition():
    assert strip_edition("21st Century Breakdown (Deluxe Edition)") == strip_edition("21st Century Breakdown")
    assert strip_edition("Hello - Single") == strip_edition("Hello")


def _entry(album, artist="Green Day", title="Basket Case"):
    return {"path": "x.m4a", "title": title, "artist": artist, "album": album, "year": "1994"}


def test_decide_statuses():
    resolved = {"source": "iTunes", "score": 110, "album": "Dookie", "year": "1994", "art_url": "u"}
    assert decide(_entry("Dookie"), resolved, set())["status"] == STATUS_OK
    assert decide(_entry("Rock from the 90s"), resolved, set())["status"] == STATUS_CHANGE
    assert decide(_entry("Some Odd Name"), resolved, {"someoddname"})["status"] == STATUS_CHANGE
    assert decide(_entry("Some Odd Name"), resolved, set())["status"] == STATUS_REVIEW
    assert decide(_entry("Rock from the 90s"), None, set())["status"] == STATUS_NOT_FOUND
    weak = {**resolved, "note": "low iTunes score and not found on MusicBrainz", "uncertain": True}
    assert decide(_entry("Rock from the 90s"), weak, set())["status"] == STATUS_REVIEW


def test_shared_album_names():
    entries = [_entry("Soft 00s"), _entry("Soft 00s", artist="Other"), _entry("Dookie")]
    assert shared_album_names(entries) == {"soft00s"}


def test_choose_musicbrainz_filters_by_title_and_flags_reissue():
    rel = lambda title, date: {  # noqa: E731
        "title": title,
        "status": "Official",
        "date": date,
        "release-group": {"id": "g", "primary-type": "Album", "secondary-types": []},
    }
    recordings = [
        {"title": "Brain Stew", "releases": [rel("Insomniac", "1995")]},
        {"title": "Good Riddance (Time of Your Life)", "releases": [rel("nimrod. XXV", "2023-01-27")]},
    ]
    best = choose_musicbrainz(recordings, "Good Riddance (Time of Your Life)")
    assert best["album"] == "nimrod. XXV"
    assert best["uncertain"] is True


def test_choose_musicbrainz_exact_title_beats_same_base_title():
    rel = lambda title, date: {  # noqa: E731
        "title": title,
        "status": "Official",
        "date": date,
        "release-group": {"id": "g", "primary-type": "Album", "secondary-types": []},
    }
    recordings = [
        {"title": "Good Riddance", "releases": [rel("Warning", "2000-10-03")]},
        {"title": "Good Riddance (Time of Your Life)", "releases": [rel("nimrod.", "1997-10-14")]},
    ]
    best = choose_musicbrainz(recordings, "Good Riddance (Time of Your Life)")
    assert best["album"] == "nimrod."
    assert "uncertain" not in best


def test_valid_track_info_rejects_bundle_numbers():
    from toolkit.audio.album_resolver import valid_track_info

    assert valid_track_info(138, 163, 1, 1) == {}
    assert valid_track_info(7, 18, 1, 1) == {"track": 7, "track_total": 18, "disc": 1, "disc_total": 1}
    assert valid_track_info(None, None) == {}


def test_choose_itunes_prefers_plain_album_over_bundle_on_tie():
    plain = _item("Last Night on Earth", "21st Century Breakdown", "2009", trackNumber=7, trackCount=18)
    bundle = _item("Last Night on Earth", "21st Century Breakdown", "2009", trackNumber=138, trackCount=163)
    best = choose_itunes([bundle, plain], "Green Day", "Last Night on Earth", "2009")
    assert best["track"] == 7 and best["track_total"] == 18


def test_write_album_tag_replaces_track_numbers(tmp_path):
    import shutil
    import subprocess

    import pytest
    from mutagen.mp4 import MP4

    from toolkit.audio.album_fixer import write_album_tag

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not available")
    dst = tmp_path / "a.m4a"
    subprocess.run(
        ["ffmpeg", "-v", "quiet", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "0.2", str(dst)],
        check=True,
    )
    assert write_album_tag(str(dst), "Dookie", "1994", {"track": 7, "track_total": 14, "disc": 1, "disc_total": 1})
    tags = MP4(str(dst))
    assert tags["©alb"] == ["Dookie"] and tags["trkn"] == [(7, 14)] and tags["disk"] == [(1, 1)]
    assert write_album_tag(str(dst), "Dookie")
    assert "trkn" not in MP4(str(dst))


def test_choose_itunes_borrows_track_from_other_edition_when_best_is_bundle():
    bundle = _item("Wake Me Up When September Ends", "American Idiot", "2004", trackNumber=115, trackCount=200)
    deluxe = _item(
        "Wake Me Up When September Ends", "American Idiot (Deluxe Edition)", "2004", trackNumber=7, trackCount=13
    )
    best = choose_itunes([bundle, deluxe], "Green Day", "Wake Me Up When September Ends", "2004")
    assert best["album"] == "American Idiot"
    assert best["track"] == 7


def test_is_compilation_name_multilingual_and_year_suffix():
    assert is_compilation_name("Músicas tristes demais para chorar e pensar na vida 2024", "Green Day")
    assert is_compilation_name("Hot Girl Summer 2024")
    assert not is_compilation_name("1989", "Taylor Swift")


def test_write_report_ignores_internal_fields(tmp_path):
    from toolkit.audio.album_fixer import write_report

    resolved = {"source": "iTunes", "score": 110, "album": "Dookie", "year": "1994", "track": 7, "track_total": 15}
    row = decide(_entry("Rock from the 90s"), resolved, set())
    path = write_report([row], report_dir=str(tmp_path))
    text = open(path, encoding="utf-8").read()
    assert "Dookie" in text and "7/15" in text and "track_no" not in text


def test_artist_titled_best_of_albums_are_compilations():
    for name in (
        "The Essential Britney Spears",
        "The Singles (Deluxe Edition)",
        "The Remix Album",
        "High Times (Singles 1992-2006) [Remastered 2006]",
    ):
        assert is_compilation_name(name, "Britney Spears"), name
    assert not is_compilation_name("FOUR (The Ultimate Edition)", "One Direction")


def test_resolve_album_prefers_musicbrainz_album_over_itunes_single(monkeypatch):
    import toolkit.audio.album_resolver as r

    monkeypatch.setattr(r, "_cache", {})
    monkeypatch.setattr(r, "_cache_loaded", True)
    single = {"source": "iTunes", "score": 95, "album": "Hollaback Girl - Single", "year": "2005", "why": ["single/EP"]}
    studio = {"source": "MusicBrainz", "score": None, "album": "Love. Angel. Music. Baby.", "year": "2004", "why": []}
    monkeypatch.setattr(r, "search_genius", lambda *a: None)
    monkeypatch.setattr(r, "search_itunes", lambda *a: dict(single))
    monkeypatch.setattr(r, "search_musicbrainz", lambda *a: dict(studio))
    got = r.resolve_album("Gwen Stefani", "Hollaback Girl", "2005")
    assert got["album"] == "Love. Angel. Music. Baby." and "single/EP" in got["note"]

    monkeypatch.setattr(r, "_cache", {})
    monkeypatch.setattr(r, "search_musicbrainz", lambda *a: None)
    got = r.resolve_album("Gwen Stefani", "Hollaback Girl", "2005")
    assert got["album"] == "Hollaback Girl - Single" and not got.get("uncertain")


def test_backup_and_restore_roundtrip(tmp_path):
    import shutil
    import subprocess

    import pytest
    from mutagen.mp4 import MP4

    from toolkit.audio.album_fixer import backup_tags, restore_backup, write_album_tag

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not available")
    f = tmp_path / "a.m4a"
    subprocess.run(
        ["ffmpeg", "-v", "quiet", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "0.2", str(f)], check=True
    )
    tags = MP4(str(f))
    tags["\xa9alb"] = "Soft 00s"
    tags["trkn"] = [(17, 22)]
    tags.save()
    row = {"file": str(f)}
    backup = backup_tags([row], report_dir=str(tmp_path))
    write_album_tag(str(f), "Dookie", "1994", {"track": 7, "track_total": 15, "disc": 1, "disc_total": 1})
    assert MP4(str(f))["\xa9alb"] == ["Dookie"]
    assert restore_backup(backup) == (1, 1)
    restored = MP4(str(f))
    assert restored["\xa9alb"] == ["Soft 00s"] and restored["trkn"] == [(17, 22)] and "disk" not in restored


def test_is_clean_change():
    from toolkit.audio.album_fixer import is_clean_change

    base = {"status": "CHANGE", "source": "iTunes", "note": ""}
    assert is_clean_change(base)
    assert not is_clean_change({**base, "source": "MusicBrainz"})
    assert not is_clean_change({**base, "note": "kept the iTunes single/EP"})
    assert not is_clean_change({**base, "status": "REVIEW"})


def test_search_genius_returns_album_and_skips_without_credentials(monkeypatch):
    import toolkit.audio.album_resolver as r

    monkeypatch.delenv("GENIUS_CLIENT_ID", raising=False)
    monkeypatch.delenv("GENIUS_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(r, "_genius_token", [])
    assert r.search_genius("Akon", "Beautiful") is None

    class Resp:
        status_code = 200

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    song = {"id": 7, "title": "Beautiful", "primary_artist": {"name": "Akon"}}
    detail = {"response": {"song": {"release_date": "2009-01-06", "album": {"name": "Freedom", "cover_art_url": "u"}}}}
    monkeypatch.setattr(r, "_genius_token", ["tok"])
    monkeypatch.setenv("GENIUS_CLIENT_ID", "id")
    monkeypatch.setenv("GENIUS_CLIENT_SECRET", "secret")
    monkeypatch.setattr(r, "_throttle", lambda *a: None)
    monkeypatch.setattr(
        r,
        "http_get",
        lambda url, **kw: Resp({"response": {"hits": [{"result": song}]}}) if url.endswith("/search") else Resp(detail),
    )
    got = r.search_genius("Akon", "Beautiful")
    assert got["album"] == "Freedom" and got["year"] == "2009" and got["source"] == "Genius"


def test_resolve_album_uses_genius_when_musicbrainz_finds_nothing(monkeypatch):
    import toolkit.audio.album_resolver as r

    monkeypatch.setattr(r, "_cache", {})
    monkeypatch.setattr(r, "_cache_loaded", True)
    monkeypatch.setattr(r, "search_itunes", lambda *a: None)
    monkeypatch.setattr(r, "search_musicbrainz", lambda *a: None)
    monkeypatch.setattr(
        r,
        "search_genius",
        lambda *a: {"source": "Genius", "score": None, "album": "Freedom", "year": "2009", "why": []},
    )
    got = r.resolve_album("Akon", "Beautiful")
    assert got["album"] == "Freedom" and "used Genius" in got["note"]


def test_genius_year_fallbacks_and_musicbrainz_skips_compilation_named_albums():
    import toolkit.audio.album_resolver as r

    assert r._genius_year({"release_date": None, "release_date_for_display": "1993"}) == "1993"
    assert r._genius_year({"release_date_for_display": "January 6, 2009"}) == "2009"
    assert r._genius_year({"album": {"release_date_components": {"year": 1997}}}) == "1997"
    assert r.is_compilation_name("Hitbreaker 2015 / 1")
    rel = {
        "title": "Hitbreaker 2015 / 1",
        "status": "Official",
        "date": "2015",
        "release-group": {"id": "g", "primary-type": "Album", "secondary-types": []},
    }
    assert choose_musicbrainz([{"title": "Shower", "releases": [rel]}], "Shower") is None


def test_valid_track_info_ignores_box_set_disc_numbers():
    from toolkit.audio.album_resolver import valid_track_info

    assert valid_track_info(3, 15, 3, 6) == {"track": 3, "track_total": 15}
    assert valid_track_info(1, 12, 2, 2) == {"track": 1, "track_total": 12, "disc": 2, "disc_total": 2}


def test_single_ep_album_tags_are_suspicious_and_become_change():
    from toolkit.audio.album_fixer import looks_suspicious

    for name in ("Don't Stop the Music - Single", "Overtime EP", "Collage - EP"):
        assert looks_suspicious(name, "Rihanna", set()), name
    assert not looks_suspicious("Good Girl Gone Bad", "Rihanna", set())
    resolved = {"source": "iTunes", "score": 110, "album": "Good Girl Gone Bad", "year": "2007", "art_url": "u"}
    entry = _entry("Don't Stop the Music - Single", artist="Rihanna", title="Don't Stop the Music")
    assert decide(entry, resolved, set())["status"] == STATUS_CHANGE
    same = {**resolved, "album": "Don't Stop the Music - Single"}
    assert decide(entry, same, set())["status"] == STATUS_OK
