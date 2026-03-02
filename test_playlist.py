import yt_dlp

url = "https://www.youtube.com/watch?v=m_zoftv7yL0&list=PL4ZipnPb-AeRHXEdkCLfoX0e4qwZGfFvC"

ydl_opts = {
    'extract_flat': True,
    'quiet': True,
    'no_warnings': True,
}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(url, download=False)
    print(f"Type: {info.get('_type')}")
    print(f"Has entries: {'entries' in info}")
    if 'entries' in info:
        print(f"Number of entries: {len(info['entries'])}")
        print(f"First entry: {info['entries'][0] if info['entries'] else 'None'}")
    else:
        print(f"Keys: {list(info.keys())[:10]}")
