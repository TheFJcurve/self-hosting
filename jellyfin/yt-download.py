import os

import yt_dlp

URLS = []
base_dir = "Music Downloads"
os.makedirs(base_dir, exist_ok=True)

ydl_opts = {
    "format": "m4a/bestaudio/best",
    "outtmpl": os.path.join(base_dir, "%(album)s", "%(title)s.%(ext)s"),
    "postprocessors": [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "m4a",
        },
        {
            "key": "FFmpegMetadata",
            "add_metadata": True,
        },
        {
            "key": "EmbedThumbnail",
            "already_have_thumbnail": False,
        },
    ],
    "cookiefile": os.path.expanduser("~/Downloads/cookies.Personal.txt"),
    "writethumbnail": True,
    "writeinfojson": False,
    "embedthumbnail": True,
    "addmetadata": True,
    "parse_metadata": "title:%(title)s,genre:%(genre)s",
    "ignoreerrors": True,
    "no_warnings": False,
    "quiet": False,
}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    try:
        error_code = ydl.download(URLS)
        if error_code == 0:
            print("\n✓ Downloads completed successfully!")
            print(f"Files saved to: {os.path.abspath(base_dir)}")
        else:
            print(f"\n⚠ Downloads completed with some errors (code: {error_code})")
    except Exception as e:
        print(f"\n✗ Error during download: {e}")
