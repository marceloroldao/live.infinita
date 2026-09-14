from __future__ import annotations

import asyncio
import os
import shutil
from collections.abc import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

UDP_INPUT = os.getenv(
    "LIVE_INFINITA_AUDIO_UDP_INPUT",
    "udp://127.0.0.1:5500?fifo_size=1000000&overrun_nonfatal=1",
)
MAX_CLIENTS = max(1, int(os.getenv("LIVE_INFINITA_AUDIO_WEB_MAX_CLIENTS", "4")))
FFMPEG_BIN = os.getenv("LIVE_INFINITA_FFMPEG_BIN", "ffmpeg")

app = FastAPI(title="Live Infinita Audio Web Bridge", version="0.2.0")
_active_streams = 0


def ffmpeg_available() -> bool:
    if os.path.isabs(FFMPEG_BIN):
        return os.path.isfile(FFMPEG_BIN) and os.access(FFMPEG_BIN, os.X_OK)
    return shutil.which(FFMPEG_BIN) is not None


def build_ffmpeg_command() -> list[str]:
    return [
        FFMPEG_BIN,
        "-hide_banner",
        "-loglevel", "error",
        "-fflags", "nobuffer",
        "-flags", "low_delay",
        "-i", UDP_INPUT,
        "-vn",
        "-c:a", "libmp3lame",
        "-b:a", "128k",
        "-ar", "48000",
        "-ac", "2",
        "-f", "mp3",
        "pipe:1",
    ]


@app.get("/health")
async def health() -> JSONResponse:
    available = ffmpeg_available()
    return JSONResponse(
        {
            "ok": available,
            "service": "live-infinita-audio-web",
            "version": app.version,
            "source": "local-program-audio",
            "input": UDP_INPUT,
            "output": "mp3/http",
            "openai_audio": False,
            "ffmpeg_available": available,
            "active_streams": _active_streams,
            "max_clients": MAX_CLIENTS,
        },
        status_code=200 if available else 503,
    )


async def mp3_stream(request: Request) -> AsyncIterator[bytes]:
    global _active_streams
    process: asyncio.subprocess.Process | None = None
    _active_streams += 1
    try:
        process = await asyncio.create_subprocess_exec(
            *build_ffmpeg_command(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        assert process.stdout is not None
        while True:
            if await request.is_disconnected():
                break
            chunk = await process.stdout.read(16384)
            if not chunk:
                break
            yield chunk
    finally:
        _active_streams = max(0, _active_streams - 1)
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()


@app.get("/live.mp3")
async def live_mp3(request: Request) -> StreamingResponse:
    if not ffmpeg_available():
        raise HTTPException(status_code=503, detail="ffmpeg unavailable")
    if _active_streams >= MAX_CLIENTS:
        raise HTTPException(status_code=503, detail="audio relay at capacity")
    return StreamingResponse(
        mp3_stream(request),
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "X-Accel-Buffering": "no",
        },
    )
