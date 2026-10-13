"""Tests for playlist parser helpers."""

from toolkit.playlists.parser import (
    clean_string,
    convert_playlist_to_txt,
    generate_search_queries,
    parse_m3u_file,
    parse_pls_file,
    parse_songs,
    pre_sanitize_song_line,
    verify_artist_match,
    verify_title_match,
    verify_track_match,
)



def test_clean_string_strips_accents():
    assert clean_string("Beyoncé") == "beyonce"


def test_clean_string_expands_censor():
    assert "fuck" in clean_string("f**k")


def test_pre_sanitize_strips_track_number():
    assert pre_sanitize_song_line("01. Hello - Adele") == "Hello - Adele"


def test_pre_sanitize_strips_video_tag():
    result = pre_sanitize_song_line("Song [Official Video] - Artist")
    assert "Official" not in result


def test_verify_title_match_exact():
    assert verify_title_match("Back to December", "Back to December")


def test_verify_title_match_rejects_unrelated():
    assert not verify_title_match("Cahaya Bulan", "Huboan Pe Ho Tu Bulan")


def test_verify_artist_match_spacing():
    assert verify_artist_match("5 Romeo", "5Romeo")


def test_verify_track_match_artist_title():
    assert verify_track_match("Taylor Swift - Back to December", "Back to December", "Taylor Swift")


def test_generate_search_queries_contains_base():
    queries = generate_search_queries("Artist - Title")
    assert any("Artist" in q and "Title" in q for q in queries)


def test_parse_pls_file(tmp_path):
    pls_content = (
        "[playlist]\n"
        "File1=Barat/artist1_-_title1.m4a\n"
        "Title1=Artist 1 - Title 1\n"
        "Length1=200\n"
        "\n"
        "File2=Barat/artist2_-_title2.m4a\n"
        "Title2=Artist 2 - Title 2\n"
        "Length2=220\n"
        "NumberOfEntries=2\n"
        "Version=2\n"
    )
    pls_file = tmp_path / "test.pls"
    pls_file.write_text(pls_content, encoding="utf-8")

    songs = parse_pls_file(str(pls_file))
    assert songs == ["Artist 1 - Title 1", "Artist 2 - Title 2"]


def test_parse_m3u_file(tmp_path):
    m3u_content = (
        "#EXTM3U\n"
        "#EXTINF:201,Adele - Hello\n"
        "Barat/adele_-_hello.m4a\n"
        "#EXTINF:180,Taylor Swift - Blank Space\n"
        "Barat/taylor_swift_-_blank_space.m4a\n"
    )
    m3u_file = tmp_path / "test.m3u"
    m3u_file.write_text(m3u_content, encoding="utf-8")

    songs = parse_m3u_file(str(m3u_file))
    assert songs == ["Adele - Hello", "Taylor Swift - Blank Space"]


def test_parse_songs_auto_routes_pls_and_m3u(tmp_path):
    pls_file = tmp_path / "sample.pls"
    pls_file.write_text("[playlist]\nTitle1=Track One\nTitle2=Track Two\n", encoding="utf-8")

    m3u_file = tmp_path / "sample.m3u"
    m3u_file.write_text("#EXTM3U\n#EXTINF:120,Track Three\nfile.mp3\n", encoding="utf-8")

    txt_file = tmp_path / "sample.txt"
    txt_file.write_text("Track Four\nTrack Five\n", encoding="utf-8")

    assert parse_songs(str(pls_file)) == ["Track One", "Track Two"]
    assert parse_songs(str(m3u_file)) == ["Track Three"]
    assert parse_songs(str(txt_file)) == ["Track Four", "Track Five"]


def test_convert_playlist_to_txt(tmp_path):
    pls_file = tmp_path / "sample.pls"
    pls_file.write_text("[playlist]\nTitle1=Artist A - Song A\nTitle2=Artist B - Song B\n", encoding="utf-8")

    output_txt = tmp_path / "sample.txt"
    converted_path = convert_playlist_to_txt(str(pls_file), str(output_txt))

    assert converted_path == str(output_txt)
    lines = output_txt.read_text(encoding="utf-8").splitlines()
    assert lines == ["Artist A - Song A", "Artist B - Song B"]

