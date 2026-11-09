"""Unified media engine routing for public, authorized media URLs.

yt-dlp remains the general-purpose default. Streamlink handles direct HLS
streams, N_m3u8DL-RE is an optional manifest downloader, and gallery-dl is
available for supported image/gallery URLs. No adapter bypasses login, DRM,
private content, geo/IP restrictions, or other access controls.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp


GALLERY_HOSTS = {
    "instagram.com", "www.instagram.com", "imgur.com", "www.imgur.com",
    "reddit.com", "www.reddit.com", "pinterest.com", "www.pinterest.com",
}
MANIFEST_SUFFIXES = (".m3u8", ".mpd")


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().rstrip(".")


def is_gallery_url(url: str) -> bool:
    host = _host(url)
    return any(host == domain or host.endswith("." + domain) for domain in GALLERY_HOSTS)


def is_hls_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.path.lower().endswith(".m3u8")


def is_manifest_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.path.lower().endswith(MANIFEST_SUFFIXES)


def select_engine(url: str, kind: str = "video", environ: dict | None = None) -> str:
    """Choose one engine deterministically; do not use blind retry chains."""
    env = os.environ if environ is None else environ
    if kind == "gallery" or is_gallery_url(url):
        return "gallery-dl"
    if is_manifest_url(url):
        binary = env.get("N_M3U8DL_RE_BIN", "N_m3u8DL-RE")
        if shutil.which(binary):
            return "N_m3u8DL-RE"
        if is_hls_url(url) and shutil.which(env.get("STREAMLINK_BIN", "streamlink")):
            return "streamlink"
    return "yt-dlp"


def _largest_file(directory: Path) -> Path:
    files = [p for p in directory.rglob("*") if p.is_file()]
    if not files:
        raise RuntimeError("لم ينشئ محرك التنزيل أي ملف.")
    return max(files, key=lambda p: p.stat().st_size)


def download_with_engine(
    url: str,
    kind: str,
    quality: str,
    output_dir: str | Path,
    job_id: str,
    max_file_size: int,
    yt_dlp_options: dict | None = None,
) -> Path:
    """Download using the selected adapter and return the resulting file."""
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    engine = select_engine(url, kind)

    if engine == "gallery-dl":
        target = folder / job_id
        target.mkdir(parents=True, exist_ok=True)
        command = [os.getenv("GALLERY_DL_BIN", "gallery-dl"), "--no-mtime", "-D", str(target), url]
        subprocess.run(command, check=True, timeout=900)
        result = _largest_file(target)
    elif engine == "N_m3u8DL-RE":
        target = folder / job_id
        target.mkdir(parents=True, exist_ok=True)
        command = [
            os.getenv("N_M3U8DL_RE_BIN", "N_m3u8DL-RE"), url,
            "--save-dir", str(target), "--save-name", job_id,
            "--tmp-dir", str(target / "tmp"), "--auto-select", "--binary-merge",
        ]
        subprocess.run(command, check=True, timeout=1800)
        result = _largest_file(target)
    elif engine == "streamlink":
        target = folder / f"{job_id}.ts"
        command = [
            os.getenv("STREAMLINK_BIN", "streamlink"), "--output", str(target),
            url, os.getenv("STREAMLINK_QUALITY", "best"),
        ]
        subprocess.run(command, check=True, timeout=1800)
        result = target
    else:
        options = dict(yt_dlp_options or {})
        options.setdefault("outtmpl", str(folder / f"{job_id}.%(ext)s"))
        options.setdefault("max_filesize", max_file_size)
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])
        candidates = [p for p in folder.glob(f"{job_id}.*") if p.is_file()]
        if not candidates:
            raise RuntimeError("لم يتم إنشاء ملف التحميل.")
        result = max(candidates, key=lambda p: p.stat().st_size)

    if not result.exists() or result.stat().st_size == 0:
        raise RuntimeError("ملف التنزيل فارغ أو غير موجود.")
    if result.stat().st_size > max_file_size:
        result.unlink(missing_ok=True)
        raise RuntimeError("حجم الملف أكبر من الحد المسموح.")
    return result
