import yt_dlp

# Use the playlist URL directly
url = "https://www.youtube.com/playlist?list=PL4ZipnPb-AeRHXEdkCLfoX0e4qwZGfFvC"

ydl_opts = {
    'extract_flat': 'in_playlist',  # Important for playlist extraction
    'quiet': True,
    'no_warnings': True,
}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(url, download=False)
    print(f"Type: {info.get('_type')}")
    print(f"Has entries: {'entries' in info}")
    if 'entries' in info:
        print(f"Number of entries: {len(info['entries'])}")
        print(f"Title: {info.get('title')}")
    else:
        print(f"Keys: {list(info.keys())[:10]}")
