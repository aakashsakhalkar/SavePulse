import os
import urllib.parse
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl
import httpx

from app.services.extractor import extract_media

app = FastAPI(
    title="SavePulse API",
    description="Universal downloader for public videos, images, and posts from Instagram, Twitter, Reddit, Facebook, and more.",
    version="1.0.0"
)

# Enable CORS for cross-origin frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ExtractRequest(BaseModel):
    url: str

@app.post("/api/extract")
async def extract_endpoint(payload: ExtractRequest):
    if not payload.url or len(payload.url.strip()) < 5:
        raise HTTPException(status_code=400, detail="Please provide a valid URL.")
    
    try:
        data = await extract_media(payload.url)
        return {"success": True, "data": data}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction error: {str(e)}")

@app.get("/api/download")
async def download_proxy(
    url: str = Query(..., description="Target media URL to proxy"),
    filename: str = Query("media_download", description="Saved file name")
):
    """Streams the media directly to the client with attachment headers to force download."""
    if not url:
        raise HTTPException(status_code=400, detail="Missing media URL.")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.google.com/"
    }

    # Ensure filename is safe
    safe_filename = urllib.parse.quote(filename.strip().replace("/", "_").replace("\\", "_"))

    async def stream_generator():
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            async with client.stream("GET", url, headers=headers) as response:
                if response.status_code != 200:
                    yield b""
                    return
                async for chunk in response.aiter_bytes(chunk_size=1024 * 64):
                    yield chunk

    # Determine Content-Type based on extension
    content_type = "application/octet-stream"
    if filename.endswith(".mp4"):
        content_type = "video/mp4"
    elif filename.endswith(".mp3"):
        content_type = "audio/mpeg"
    elif filename.endswith(".jpg") or filename.endswith(".jpeg"):
        content_type = "image/jpeg"
    elif filename.endswith(".png"):
        content_type = "image/png"
    elif filename.endswith(".webp"):
        content_type = "image/webp"

    return StreamingResponse(
        stream_generator(),
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_filename}"; filename*=UTF-8\'\'{safe_filename}',
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )

# Static file serving for local development
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.mount("/css", StaticFiles(directory=os.path.join(static_dir, "css")), name="css")
    app.mount("/js", StaticFiles(directory=os.path.join(static_dir, "js")), name="js")

@app.get("/favicon.svg")
async def get_favicon():
    favicon_path = os.path.join(static_dir, "favicon.svg")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path)
    raise HTTPException(status_code=404, detail="Favicon not found")

@app.get("/")
async def root():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "SavePulse API is running."}
