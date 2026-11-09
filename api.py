"""Authenticated HTTP API for the standalone unified media download engine."""
from __future__ import annotations

import ipaddress
import os
import shutil
import socket
import tempfile
import uuid
from pathlib import Path
from urllib.parse import quote, urlparse

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from smart_download_engine import download_with_engine

app = FastAPI(title="Unified Media Download API", version="1.0.0")
API_KEY = os.getenv("API_KEY", "").strip()
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "100"))
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024


class DownloadRequest(BaseModel):
    url: str = Field(min_length=8, max_length=4096)
    kind: str = Field(pattern="^(video|audio)$")
    quality: str = Field(default="best", pattern="^(best|144|240|360|480|720|1080|1440|2160)$")


def validate_public_url(raw: str) -> None:
    parsed = urlparse(raw.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(400, "A valid HTTP(S) URL is required.")
    if parsed.username or parsed.password:
        raise HTTPException(400, "URLs containing credentials are not accepted.")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"}:
        raise HTTPException(400, "Local URLs are not accepted.")
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            raise HTTPException(400, "Only public URLs are accepted.")
    except ValueError:
        try:
            records = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
            if not records or any(not ipaddress.ip_address(item[4][0]).is_global for item in records):
                raise HTTPException(400, "Only public URLs are accepted.")
        except OSError:
            raise HTTPException(400, "The URL host could not be resolved.")


@app.get("/health")
async def health():
    return {"ok": True, "service": "unified-media-engine"}


@app.post("/download")
async def download(request: DownloadRequest, x_api_key: str | None = Header(default=None)):
    if not API_KEY:
        raise HTTPException(503, "API_KEY is not configured on the engine service.")
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(401, "Invalid API key.")
    validate_public_url(request.url)

    workdir = Path(tempfile.mkdtemp(prefix="unified-engine-"))
    try:
        result = download_with_engine(
            url=request.url,
            kind=request.kind,
            quality=request.quality,
            output_dir=workdir,
            job_id=uuid.uuid4().hex,
            max_file_size=MAX_FILE_SIZE,
            yt_dlp_options={
                "quiet": True, "no_warnings": True, "noplaylist": True,
                "socket_timeout": 30, "retries": 3,
                "fragment_retries": 5, "extractor_retries": 3,
            },
        )
        if not result.is_file() or result.stat().st_size <= 0:
            raise RuntimeError("Download produced no file.")
        return FileResponse(
            path=str(result),
            filename=result.name,
            media_type="application/octet-stream",
            headers={
                "X-Filename": quote(result.name, safe=""),
                "X-Media-Title": quote(result.stem[:100], safe=""),
            },
            background=BackgroundTask(shutil.rmtree, workdir, ignore_errors=True),
        )
    except HTTPException:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(502, f"Download engine failed: {type(exc).__name__}: {str(exc)[:350]}")
