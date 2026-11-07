# Universal Media Downloader Bot

Telegram bot using Python, yt-dlp and FFmpeg. Offers available video quality choices and MP3 extraction for public URLs you are authorized to download. It does not bypass DRM or access controls.

## Deploy on Railway
1. Create a Railway project and deploy this GitHub repository.
2. Add a service variable named BOT_TOKEN with the newly rotated token from BotFather. Never commit the token.
3. Optionally set MAX_FILE_SIZE_MB (default 49).
4. Deploy. The service uses Telegram long polling; no public domain or webhook is needed.

## Local run
Install FFmpeg, install requirements.txt, set BOT_TOKEN, and run python main.py.
