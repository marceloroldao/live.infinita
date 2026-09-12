from __future__ import annotations

import asyncio
import os
import subprocess
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

UDP_INPUT = os.getenv(
    "LIVE_INFINITA_AUDIO_UDP_INPUT",
    "udp://127.0.0.1:5500?fifo_size=1000000&overrun_nonfatal=1",
)

app = FastAPI(title="Live Infinita Audio Web Bridge", version="0.1.0")


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({
        "ok": True,
        "service": "live-infinita-audio-web",
        "source": "local-program-audio",
        "input": "udp://127.0.0.1:5500",
        "output": "mp3/http",
        "openai_audio": False,
    })


async def mp3_stream(request: Request) -> AsyncIterator[bytes]:
    cmd = [
        "ffmpeg",
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
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        assert process.stdout is not None
        while True:
            if await request.is_disconnected():
                break
            chunk = await process.stdout.read(16384)
            if not chunk:
                break
            yield chunk
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()


@app.get("/live.mp3")
async def live_mp3(request: Request) -> StreamingResponse:
    return StreamingResponse(
        mp3_stream(request),
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )
