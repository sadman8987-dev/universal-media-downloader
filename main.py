import asyncio
import logging
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from smart_download_engine import download_with_engine, is_gallery_url
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("media-downloader")

BOT_TOKEN = os.environ["BOT_TOKEN"]
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "49"))
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024
DOWNLOAD_DIR = Path(tempfile.gettempdir()) / "media-downloader"
DOWNLOAD_DIR.mkdir(exist_ok=True)
JOBS = {}
DOWNLOAD_LOCK = asyncio.Lock()


def inspect_url(url: str):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "socket_timeout": 25,
        "retries": 3,
        "extractor_retries": 3,
        "fragment_retries": 3,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def is_tiktok_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    return host == "tiktok.com" or host.endswith(".tiktok.com")


def download_media(url: str, kind: str, quality: str, job_id: str):
    output = str(DOWNLOAD_DIR / f"{job_id}.%(ext)s")
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "outtmpl": output,
        "overwrites": True,
        "max_filesize": MAX_FILE_SIZE,
        "socket_timeout": 25,
        "retries": 3,
        "fragment_retries": 3,
        "extractor_retries": 3,
    }
    if kind == "gallery":
        pass
    elif kind == "audio":
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
    else:
        height = int(quality)
        opts["format"] = (
            f"bestvideo[height<={height}]+bestaudio/"
            f"best[height<={height}]/best"
        )
        opts["merge_output_format"] = "mp4"
    return download_with_engine(
        url=url, kind=kind, quality=quality, output_dir=DOWNLOAD_DIR,
        job_id=job_id, max_file_size=MAX_FILE_SIZE, yt_dlp_options=opts,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أهلاً بك في Media Downloader 📥\n"
        "ابعت رابط فيديو عام تملك حق تنزيله، وهعرض لك الجودات المتاحة.\n"
        "يمكنك تنزيل الصوت بصيغة MP3."
    )


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_text = (update.message.text or "").strip()
    match = re.search(r"https?://\S+", raw_text)
    url = match.group(0).rstrip(".,!?;:)]}>") if match else raw_text
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        await update.message.reply_text("من فضلك ابعت رابط صحيح يبدأ بـ http أو https.")
        return

    status = await update.message.reply_text("⏳ بفحص الرابط...")
    try:
        info = await asyncio.to_thread(inspect_url, url)
        if info.get("_type") == "playlist" or info.get("entries"):
            await status.edit_text("قوائم التشغيل غير مدعومة حالياً. ابعت رابط فيديو واحد.")
            return

        title = (info.get("title") or "Video")[:90]
        formats = info.get("formats", [])
        heights = sorted({
            int(f["height"]) for f in formats
            if f.get("height") and f.get("vcodec") != "none"
        }, reverse=True)
        choices = [h for h in (1080, 720, 480, 360) if any(x >= h for x in heights)]
        if not choices and heights:
            choices = [max(heights)]
        if not choices:
            await status.edit_text("لم أجد جودة فيديو قابلة للتنزيل بدون دمج ملفات.")
            return

        key = f"{update.effective_user.id}:{update.effective_chat.id}"
        JOBS[key] = {"url": url, "title": title}
        buttons = [[InlineKeyboardButton(f"🎬 {h}p", callback_data=f"v:{h}")] for h in choices]
        buttons.append([InlineKeyboardButton("🎵 تنزيل الصوت", callback_data="audio")])
        if is_gallery_url(url):
            buttons.append([InlineKeyboardButton("🖼 تنزيل الصور/الألبوم", callback_data="gallery")])
        await status.edit_text(f"{title}\nاختار الجودة:", reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        log.exception("Inspect failed")
        detail = str(e).lower()
        if is_gallery_url(url):
            key = f"{update.effective_user.id}:{update.effective_chat.id}"
            JOBS[key] = {"url": url, "title": "Media gallery"}
            buttons = [[InlineKeyboardButton("🖼 تنزيل الصور/الألبوم", callback_data="gallery")]]
            await status.edit_text(
                "تعذّر فحص الألبوم كفيديو. يمكن تجربة تنزيل الصور العامة المتاحة:",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            return
        if is_tiktok_url(url):
            key = f"{update.effective_user.id}:{update.effective_chat.id}"
            JOBS[key] = {"url": url, "title": "TikTok video"}
            buttons = [
                [InlineKeyboardButton(f"🎬 {h}p", callback_data=f"v:{h}")]
                for h in (720, 480, 360)
            ]
            buttons.append([InlineKeyboardButton("🎵 تنزيل الصوت MP3", callback_data="audio")])
            if "unexpected response" in detail:
                notice = (
                    "TikTok أرجع استجابة غير متوقعة أثناء فحص الرابط. جرّب التنزيل مباشرة؛ "
                    "إذا رفض الموقع الرابط فلن يكتمل."
                )
            else:
                notice = (
                    "تعذّر فحص صيغ TikTok تلقائيًا. جرّب إحدى خيارات التنزيل؛ "
                    "إذا كان الرابط مقيّدًا أو رفضه TikTok فلن يكتمل التنزيل."
                )
            await status.edit_text(
                notice,
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            return
        await status.edit_text(f"تعذر فحص الرابط: {str(e)[:250]}")


async def choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    key = f"{query.from_user.id}:{query.message.chat_id}"
    job = JOBS.get(key)
    if not job:
        await query.edit_message_text("الرابط انتهت صلاحيته. ابعته مرة تانية.")
        return

    kind = "gallery" if query.data == "gallery" else ("audio" if query.data == "audio" else "video")
    quality = "0" if kind in {"audio", "gallery"} else query.data.split(":", 1)[1]
    await query.edit_message_text("⬇️ جاري التحميل... قد يستغرق بعض الوقت.")
    job_id = f"{query.from_user.id}_{query.message.message_id}"
    path = None

    try:
        async with DOWNLOAD_LOCK:
            path = await asyncio.to_thread(download_media, job["url"], kind, quality, job_id)
            if path.stat().st_size > MAX_FILE_SIZE:
                raise RuntimeError(f"حجم الملف أكبر من الحد المسموح ({MAX_FILE_SIZE_MB} MB).")
            with path.open("rb") as media:
                if kind == "audio":
                    await query.message.reply_audio(
                        audio=media, title=job["title"][:64],
                        filename=f"{job_id}.mp3", caption="تم التحميل بنجاح ✅"
                    )
                else:
                    if path.suffix.lower() in {".mp4", ".m4v"}:
                        await query.message.reply_video(
                            video=media, caption="تم التحميل بنجاح ✅",
                            supports_streaming=True
                        )
                    else:
                        await query.message.reply_document(
                            document=media, filename=path.name,
                            caption="تم التحميل بنجاح ✅"
                        )
    except Exception as e:
        log.exception("Download failed")
        detail = str(e).lower()
        if is_tiktok_url(job["url"]) and "unexpected response" in detail:
            message = (
                "TikTok لم يسلّم بيانات الفيديو لهذا الرابط. تأكد أن الفيديو عام والرابط حديث، "
                "ثم أعد المحاولة لاحقًا بعد تحديث yt-dlp. قد يكون المحتوى محذوفًا أو مقيّدًا."
            )
        elif is_tiktok_url(job["url"]):
            message = (
                "تعذّر تنزيل فيديو TikTok. تأكد أن الفيديو عام والرابط صحيح، ثم حدّث البوت "
                "وأعد المحاولة. لا يتجاوز البوت تسجيل الدخول أو القيود."
            )
        else:
            message = f"حصلت مشكلة أثناء التحميل: {str(e)[:300]}"
        await query.message.reply_text(message)
    finally:
        if path and path.exists():
            path.unlink(missing_ok=True)
        JOBS.pop(key, None)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ابعت رابط فيديو عام مسموح لك بتنزيله، بما في ذلك TikTok، ثم اختار الجودة "
        "أو تنزيل الصوت MP3. لا يدعم تجاوز DRM أو تسجيل الدخول أو القيود."
    )


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(choose, pattern=r"^(audio|gallery|v:\d+)$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    log.info("Media Downloader bot starting with long polling")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
