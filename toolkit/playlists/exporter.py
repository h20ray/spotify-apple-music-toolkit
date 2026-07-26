"""
Playlist Exporter Module.
Handles writing playlist files in various formats: TSV, M3U8, XML.
"""

def export_apple_tsv(playlist_name, tracks, output_path):
    """Export official Apple Music native TSV Text Playlist format (.txt)."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("Name\tArtist\tComposer\tAlbum\tGenre\tSize\tTime\tDisc Number\tDisc Count\tTrack Number\tTrack Count\tYear\tDate Modified\tDate Added\tBit Rate\tSample Rate\tVolume Adjustment\tKind\tEqualizer\tComments\tPlay Count\tLast Played\tSkip Count\tLast Skipped\tMy Rating\tLocation\n")

        for item in tracks:
            title = item.get('trackName', '')
            artist = item.get('artistName', '')
            album = item.get('collectionName', '')
            duration_sec = int(item.get('trackTimeMillis', 0) / 1000)

            f.write(f"{title}\t{artist}\t\t{album}\t\t\t{duration_sec}\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\n")

def export_m3u8(playlist_name, tracks, output_path):
    """Export Apple Music / Spotify compatible UTF-8 M3U playlist file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        f.write(f"#PLAYLIST:{playlist_name}\n\n")

        for item in tracks:
            artist = item.get('artistName', 'Unknown Artist')
            title = item.get('trackName', 'Unknown Title')
            duration_sec = int(item.get('trackTimeMillis', 0) / 1000)

            f.write(f"#EXTINF:{duration_sec},{artist} - {title}\n\n")

def export_apple_xml(playlist_name, tracks, output_path):
    """Export iTunes / Apple Music Library XML playlist file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n')
        f.write('<plist version="1.0">\n')
        f.write('<dict>\n')
        f.write('    <key>Major Version</key><integer>1</integer>\n')
        f.write('    <key>Minor Version</key><integer>1</integer>\n')
        f.write('    <key>Application Version</key><string>12.12.0</string>\n')
        f.write('    <key>Features</key><integer>5</integer>\n')
        f.write('    <key>Show Content Ratings</key><true/>\n')
        f.write('    <key>Tracks</key>\n')
        f.write('    <dict>\n')

        for idx, item in enumerate(tracks, 1):
            track_id = item.get('trackId', idx)
            title = item.get('trackName', '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            artist = item.get('artistName', '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            album = item.get('collectionName', '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            duration = item.get('trackTimeMillis', 0)

            f.write(f'        <key>{track_id}</key>\n')
            f.write('        <dict>\n')
            f.write(f'            <key>Track ID</key><integer>{track_id}</integer>\n')
            f.write(f'            <key>Name</key><string>{title}</string>\n')
            f.write(f'            <key>Artist</key><string>{artist}</string>\n')
            f.write(f'            <key>Album</key><string>{album}</string>\n')
            f.write(f'            <key>Total Time</key><integer>{duration}</integer>\n')
            f.write('        </dict>\n')

        f.write('    </dict>\n')
        f.write('    <key>Playlists</key>\n')
        f.write('    <array>\n')
        f.write('        <dict>\n')
        f.write(f'            <key>Name</key><string>{playlist_name.replace("&", "&amp;")}</string>\n')
        f.write('            <key>Playlist Items</key>\n')
        f.write('            <array>\n')
        for item in tracks:
            t_id = item.get('trackId', 0)
            f.write('                <dict>\n')
            f.write(f'                    <key>Track ID</key><integer>{t_id}</integer>\n')
            f.write('                </dict>\n')
        f.write('            </array>\n')
        f.write('        </dict>\n')
        f.write('    </array>\n')
        f.write('</dict>\n')
        f.write('</plist>\n')
