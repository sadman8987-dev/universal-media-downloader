# Universal Media Downloader Bot

Telegram bot using Python, yt-dlp and FFmpeg. Offers available video quality choices and MP3 extraction for public URLs you are authorized to download, including public TikTok links. TikTok may change its response format or restrict some videos; the bot retries extraction and reports a useful error but does not bypass login, DRM or access controls.

## Deploy on Railway
1. Create a Railway project and deploy this GitHub repository.
2. Add a service variable named BOT_TOKEN with the newly rotated token from BotFather. Never commit the token.
3. Optionally set MAX_FILE_SIZE_MB (default 49).
4. Deploy or redeploy after pushing code changes. The service uses Telegram long polling; no public domain or webhook is needed. Docker installs FFmpeg for MP3 conversion and video/audio merging.

## Local run
Install FFmpeg, install requirements.txt, set BOT_TOKEN, and run `python main.py`.

For TikTok errors, first confirm the post is public and the link is current, then rebuild/redeploy so the latest `yt-dlp` dependency is installed. Some TikTok links may remain unavailable if the post is private, deleted, region-restricted, or TikTok changes its service.


## Unified download engines

The Telegram bot routes supported links through `smart_download_engine.py`:

- **yt-dlp** is the default general-purpose extractor and downloader.
- **Streamlink** is selected for direct HLS `.m3u8` streams when Streamlink is installed.
- **N_m3u8DL-RE** is preferred for direct HLS/DASH manifests only when its executable is installed and available on `PATH`.
- **gallery-dl** handles supported public image/gallery URLs (including supported Instagram, Imgur, Reddit, and Pinterest posts).
- **FFmpeg** remains the media post-processing tool used by yt-dlp for audio extraction and merging.

Streamlink and gallery-dl are installed by the Docker build through `requirements.txt`. N_m3u8DL-RE is an optional external executable: provide a compatible Linux binary in the container and set `N_M3U8DL_RE_BIN` to its path/name. If it is absent, HLS falls back to Streamlink when available; other URLs use yt-dlp. The router deliberately avoids blind retries on access-denied, login-required, private, DRM-protected, or geo/IP-restricted content.

Run routing tests with:

```bash
python -m unittest discover -s tests -v
```

The engine package is integrated into this standalone repository only. It does not change or deploy the separate production video-downloader bot.
