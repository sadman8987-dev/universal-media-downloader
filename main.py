import os
import asyncio
import logging
import tempfile
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import yt_dlp

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("media-downloader")

BOT_TOKEN = os.environ["BOT_TOKEN"]
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "49"))
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024
DOWNLOAD_DIR = Path(tempfile.gettempdir()) / "media-downloader"
DOWNLOAD_DIR.mkdir(exist_ok=True)
JOBS = {}

def inspect_url(url: str):
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)

def download_media(url: str, kind: str, quality: str, job_id: str):
    output = str(DOWNLOAD_DIR / f"{job_id}.%(ext)s")
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True,
            "outtmpl": output, "overwrites": True, "max_filesize": MAX_FILE_SIZE}
    if kind == "audio":
        opts.update({"format": "bestaudio/best", "postprocessors": [{
            "key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]})
    else:
        height = int(quality)
        opts.update({"format": f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best[height<={height}]",
                     "merge_output_format": "mp4"})
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    files = [p for p in DOWNLOAD_DIR.glob(f"{job_id}.*") if p.is_file()]
    if not files:
        raise RuntimeError("لم يتم إنشاء ملف التحميل.")
    return max(files, key=lambda p: p.stat().st_size)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً بك في Media Downloader 📥\nابعت رابط فيديو عام تملك حق تنزيله، وهعرض لك الجودات المتاحة.\nيمكنك أيضاً اختيار MP3 للصوت فقط.")

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = (update.message.text or "").strip()
    if not url.startswith(("https://", "http://")):
        await update.message.reply_text("من فضلك ابعت رابط يبدأ بـ http أو https.")
        return
    status = await update.message.reply_text("⏳ بفحص الرابط...")
    try:
        info = await asyncio.to_thread(inspect_url, url)
        if info.get("_type") == "playlist" or info.get("entries"):
            await status.edit_text("قوائم التشغيل غير مدعومة حالياً. ابعت رابط فيديو واحد.")
            return
        title = (info.get("title") or "Video")[:90]
        heights = sorted({int(f["height"]) for f in info.get("formats", [])
                          if f.get("height") and f.get("vcodec") != "none"}, reverse=True)
        choices = [h for h in (1080, 720, 480, 360) if any(x >= h for x in heights)]
        if not choices:
            choices = [max(heights)] if heights else [360]
        key = f"{update.effective_user.id}:{update.effective_chat.id}"
        JOBS[key] = {"url": url, "title": title}
        buttons = [[InlineKeyboardButton(f"🎬 {h}p", callback_data=f"v:{h}")] for h in choices]
        buttons.append([InlineKeyboardButton("🎵 MP3 صوت فقط", callback_data="audio")])
        await status.edit_text(f"{title}\nاختار الجودة:", reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        log.exception("Inspect failed")
        await status.edit_text(f"تعذر فحص الرابط: {str(e)[:250]}")

async def choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    key = f"{query.from_user.id}:{query.message.chat_id}"
    job = JOBS.get(key)
    if not job:
        await query.edit_message_text("الرابط انتهت صلاحيته. ابعته مرة تانية.")
        return
    kind = "audio" if query.data == "audio" else "video"
    quality = "0" if kind == "audio" else query.data.split(":", 1)[1]
    await query.edit_message_text("⬇️ جاري التحميل... قد يستغرق بعض الوقت.")
    job_id = f"{query.from_user.id}_{query.message.message_id}"
    path = None
    try:
        path = await asyncio.to_thread(download_media, job["url"], kind, quality, job_id)
        if path.stat().st_size > MAX_FILE_SIZE:
            raise RuntimeError(f"حجم الملف أكبر من الحد المسموح ({MAX_FILE_SIZE_MB} MB).")
        with path.open("rb") as media:
            if kind == "audio":
                await query.message.reply_audio(audio=media, title=job["title"][:64], caption="تم التحميل بنجاح ✅")
            else:
                await query.message.reply_video(video=media, caption="تم التحميل بنجاح ✅", supports_streaming=True)
    except Exception as e:
        log.exception("Download failed")
        await query.message.reply_text(f"حصلت مشكلة أثناء التحميل: {str(e)[:300]}")
    finally:
        if path and path.exists():
            path.unlink(missing_ok=True)
        JOBS.pop(key, None)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ابعت رابط فيديو عام مسموح لك بتنزيله، ثم اختار الجودة أو MP3. لا يدعم تجاوز DRM أو القيود.")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_handler(CallbackQueryHandler(choose))
    log.info("Bot is starting")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
