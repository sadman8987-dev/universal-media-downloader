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
