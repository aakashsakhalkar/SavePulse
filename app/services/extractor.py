import html
import json
import re
import urllib.parse
from typing import Any, Dict, List, Optional
import httpx
import yt_dlp
from yt_dlp.extractor.instagram import InstagramIE


def detect_platform(url: str) -> str:
    url_lower = url.lower()
    if "instagram.com" in url_lower or "instagr.am" in url_lower:
        return "instagram"
    elif "twitter.com" in url_lower or "x.com" in url_lower:
        return "twitter"
    elif "reddit.com" in url_lower or "redd.it" in url_lower:
        return "reddit"
    elif "facebook.com" in url_lower or "fb.watch" in url_lower or "fb.com" in url_lower:
        return "facebook"
    elif "tiktok.com" in url_lower:
        return "tiktok"
    elif "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    elif "pinterest.com" in url_lower or "pin.it" in url_lower:
        return "pinterest"
    return "general"


def format_filesize(size_in_bytes: Optional[int]) -> str:
    if not size_in_bytes:
        return "HD"
    for unit in ["B", "KB", "MB", "GB"]:
        if size_in_bytes < 1024.0:
            return f"{size_in_bytes:.1f} {unit}"
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.1f} GB"


async def extract_reddit_direct(url: str) -> Optional[Dict[str, Any]]:
    """Fast-path extractor for Reddit posts using public JSON endpoints."""
    clean_url = url.split("?")[0].rstrip("/")
    json_url = f"{clean_url}.json"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(json_url, headers=headers)
            if resp.status_code != 200:
                return None
            data = resp.json()

        post_data = data[0]["data"]["children"][0]["data"]
        title = post_data.get("title", "Reddit Post")
        author = post_data.get("author", "u/anonymous")
        thumbnail = post_data.get("thumbnail", "")
        if not thumbnail.startswith("http"):
            thumbnail = ""

        items: List[Dict[str, Any]] = []

        # 1. Check Reddit native video (v.redd.it)
        if post_data.get("is_video") and post_data.get("media"):
            video_data = post_data["media"].get("reddit_video", {})
            fallback_url = video_data.get("fallback_url")
            height = video_data.get("height", "720")
            if fallback_url:
                items.append({
                    "id": "reddit_video_best",
                    "type": "video",
                    "quality": f"{height}p (Video)",
                    "ext": "mp4",
                    "url": fallback_url,
                    "filesize_str": "HD"
                })

        # 2. Check for gallery / multi-image post
        elif post_data.get("is_gallery") and post_data.get("media_metadata"):
            media_meta = post_data["media_metadata"]
            for idx, (media_id, meta) in enumerate(media_meta.items(), 1):
                if meta.get("status") == "valid":
                    s = meta.get("s", {})
                    img_url = s.get("u") or s.get("gif")
                    if img_url:
                        img_url = img_url.replace("&amp;", "&")
                        items.append({
                            "id": f"gallery_img_{idx}",
                            "type": "image",
                            "quality": f"Image #{idx} ({s.get('x', '')}x{s.get('y', '')})",
                            "ext": "jpg",
                            "url": img_url,
                            "filesize_str": "Original"
                        })
            if not thumbnail and items:
                thumbnail = items[0]["url"]

        # 3. Check for single image / i.redd.it or direct URL
        elif post_data.get("post_hint") == "image" or post_data.get("url", "").endswith((".jpg", ".png", ".gif", ".webp")):
            img_url = post_data.get("url", "")
            items.append({
                "id": "reddit_single_img",
                "type": "image",
                "quality": "Original Image",
                "ext": img_url.split(".")[-1] if "." in img_url else "jpg",
                "url": img_url,
                "filesize_str": "Full Quality"
            })
            if not thumbnail:
                thumbnail = img_url

        if items:
            return {
                "platform": "reddit",
                "title": title,
                "author": f"u/{author}",
                "thumbnail": thumbnail or (items[0]["url"] if items[0]["type"] == "image" else ""),
                "media_type": items[0]["type"] if len(items) == 1 else "gallery",
                "items": items
            }
    except Exception:
        pass
    return None


async def extract_instagram_fallback(url: str) -> Optional[Dict[str, Any]]:
    """Direct HTTP fallback for Instagram posts when yt-dlp is blocked by IP."""
    match = re.search(r'instagram\.com/(?:p|reel|tv|share/p)/([^/?#&]+)', url)
    if not match:
        return None
    shortcode = match.group(1)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            media_url = f"https://www.instagram.com/p/{shortcode}/media/?size=l"
            resp = await client.get(media_url, headers=headers)
            if resp.status_code == 200:
                final_img_url = str(resp.url)
                return {
                    "platform": "instagram",
                    "title": "Instagram Media",
                    "author": "@instagram_user",
                    "thumbnail": final_img_url,
                    "media_type": "image",
                    "items": [
                        {
                            "id": "ig_fallback_photo",
                            "type": "image",
                            "quality": "Full HD Photo",
                            "ext": "jpg",
                            "url": final_img_url,
                            "filesize_str": "Original"
                        }
                    ]
                }
    except Exception:
        pass
    return None


def extract_instagram(url: str) -> Dict[str, Any]:
    """Robust extractor for Instagram supporting single videos, photos, and 20-item carousels."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    }

    ydl = yt_dlp.YoutubeDL(ydl_opts)
    ie = InstagramIE(ydl)
    
    info = ie._real_extract(url)
    if not info:
        raise ValueError("Could not extract Instagram post data.")

    title = info.get("title") or info.get("description") or "Instagram Post"
    if title and len(title) > 120:
        title = title[:117] + "..."

    author = info.get("uploader") or info.get("uploader_id") or info.get("channel") or "@instagram_user"
    thumbnail = info.get("thumbnail") or ""

    items: List[Dict[str, Any]] = []

    # Check if this is a carousel with multiple entries
    entries = info.get("entries")
    if entries:
        for idx, entry in enumerate(entries, 1):
            if not entry:
                continue

            entry_id = entry.get("id") or f"ig_item_{idx}"
            entry_formats = entry.get("formats", [])
            entry_thumbnails = entry.get("thumbnails", [])
            
            # 1. Video Entry
            video_url = None
            if entry_formats:
                for f in reversed(entry_formats):
                    if f.get("url") and f.get("vcodec") != "none":
                        video_url = f.get("url")
                        break
            if not video_url and entry.get("url") and entry.get("ext") in ["mp4", "webm"]:
                video_url = entry.get("url")

            if video_url:
                thumb = entry.get("thumbnail") or (entry_thumbnails[-1]["url"] if entry_thumbnails else "")
                items.append({
                    "id": f"media_item_{idx}",
                    "type": "video",
                    "quality": f"Video #{idx} (HD)",
                    "ext": "mp4",
                    "url": video_url,
                    "thumbnail": thumb,
                    "filesize_str": format_filesize(entry.get("filesize") or entry.get("filesize_approx"))
                })
                if not thumbnail and thumb:
                    thumbnail = thumb

            # 2. Photo Entry
            else:
                img_url = ""
                if entry_thumbnails:
                    img_url = entry_thumbnails[-1].get("url")
                if not img_url and entry.get("url"):
                    img_url = entry.get("url")

                if img_url:
                    items.append({
                        "id": f"media_item_{idx}",
                        "type": "image",
                        "quality": f"Photo #{idx} (Full HD)",
                        "ext": "jpg",
                        "url": img_url,
                        "thumbnail": img_url,
                        "filesize_str": "Original"
                    })
                    if not thumbnail:
                        thumbnail = img_url

    # Single Post (Single Video or Single Photo)
    else:
        formats = info.get("formats", [])
        video_formats = []

        for fmt in formats:
            fmt_url = fmt.get("url")
            if not fmt_url:
                continue
            if fmt.get("vcodec", "none") != "none":
                height = fmt.get("height") or 1080
                video_formats.append({
                    "id": f"video_{fmt.get('format_id')}",
                    "type": "video",
                    "quality": f"{height}p (MP4)",
                    "ext": "mp4",
                    "url": fmt_url,
                    "filesize_str": format_filesize(fmt.get("filesize") or fmt.get("filesize_approx"))
                })

        if video_formats:
            items.extend(video_formats[:4])
        else:
            # Single photo post
            thumbnails = info.get("thumbnails", [])
            img_url = (thumbnails[-1]["url"] if thumbnails else "") or info.get("url")
            if img_url:
                items.append({
                    "id": "single_photo",
                    "type": "image",
                    "quality": "Original Photo (Full HD)",
                    "ext": "jpg",
                    "url": img_url,
                    "filesize_str": "Original"
                })
                if not thumbnail:
                    thumbnail = img_url

    if not items:
        raise ValueError("No media items extracted.")

    media_type = "gallery" if len(items) > 1 else (items[0]["type"] if items else "image")

    return {
        "platform": "instagram",
        "title": title,
        "author": author,
        "thumbnail": thumbnail,
        "media_type": media_type,
        "items": items
    }


def extract_with_ytdlp(url: str, platform: str) -> Dict[str, Any]:
    """Universal extractor for TikTok, YouTube, Twitter/X, Facebook, and other platforms."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "skip_download": True,
        "format": "bestvideo+bestaudio/best",
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info:
            raise ValueError("Unable to extract media information from this URL.")

        title = info.get("title") or info.get("description") or f"{platform.title()} Media"
        if title and len(title) > 120:
            title = title[:117] + "..."

        author = info.get("uploader") or info.get("uploader_id") or info.get("channel") or "Unknown"
        thumbnail = info.get("thumbnail") or ""

        items: List[Dict[str, Any]] = []

        entries = info.get("entries")
        if entries:
            for idx, entry in enumerate(entries, 1):
                if not entry:
                    continue
                entry_url = entry.get("url") or entry.get("webpage_url")
                entry_thumb = entry.get("thumbnail", "")
                entry_ext = entry.get("ext", "mp4")
                items.append({
                    "id": f"media_item_{idx}",
                    "type": "video" if entry_ext in ["mp4", "webm", "mkv"] else "image",
                    "quality": f"Item #{idx} ({entry.get('resolution') or 'HD'})",
                    "ext": entry_ext,
                    "url": entry_url,
                    "filesize_str": format_filesize(entry.get("filesize") or entry.get("filesize_approx"))
                })
                if not thumbnail and entry_thumb:
                    thumbnail = entry_thumb
        else:
            formats = info.get("formats", [])
            video_formats = []
            audio_formats = []

            for fmt in formats:
                fmt_url = fmt.get("url")
                if not fmt_url:
                    continue

                vcodec = fmt.get("vcodec", "none")
                acodec = fmt.get("acodec", "none")
                ext = fmt.get("ext", "mp4")
                height = fmt.get("height")
                filesize = fmt.get("filesize") or fmt.get("filesize_approx")
                format_note = fmt.get("format_note", "")

                if vcodec != "none":
                    res_label = f"{height}p" if height else format_note or "Video"
                    video_formats.append({
                        "id": f"video_{fmt.get('format_id')}",
                        "type": "video",
                        "quality": res_label,
                        "ext": ext if ext != "unknown_video" else "mp4",
                        "url": fmt_url,
                        "height": height or 0,
                        "tbr": fmt.get("tbr") or 0,
                        "filesize_str": format_filesize(filesize)
                    })
                elif acodec != "none" and vcodec == "none":
                    audio_formats.append({
                        "id": f"audio_{fmt.get('format_id')}",
                        "type": "audio",
                        "quality": f"Audio ({fmt.get('abr', 128):.0f} kbps)",
                        "ext": "mp3" if ext in ["m4a", "aac", "mp3"] else ext,
                        "url": fmt_url,
                        "filesize_str": format_filesize(filesize)
                    })

            video_formats.sort(key=lambda x: (x.get("height", 0), x.get("tbr", 0)), reverse=True)

            seen_resolutions = set()
            for v_fmt in video_formats:
                q = v_fmt["quality"]
                if q not in seen_resolutions:
                    seen_resolutions.add(q)
                    items.append({
                        "id": v_fmt["id"],
                        "type": "video",
                        "quality": f"{q} (MP4)",
                        "ext": "mp4",
                        "url": v_fmt["url"],
                        "filesize_str": v_fmt["filesize_str"]
                    })
                if len(items) >= 4:
                    break

            if not items and info.get("url"):
                ext = info.get("ext", "mp4")
                items.append({
                    "id": "direct_best",
                    "type": "video" if ext in ["mp4", "webm", "mkv"] else "image",
                    "quality": "Best Quality",
                    "ext": ext,
                    "url": info["url"],
                    "filesize_str": format_filesize(info.get("filesize"))
                })

            if audio_formats:
                best_audio = audio_formats[0]
                items.append({
                    "id": "audio_best",
                    "type": "audio",
                    "quality": "Audio Only (MP3)",
                    "ext": "mp3",
                    "url": best_audio["url"],
                    "filesize_str": best_audio["filesize_str"]
                })

        media_type = "gallery" if entries and len(entries) > 1 else ("video" if any(i.get("type") == "video" for i in items) else "image")

        return {
            "platform": platform,
            "title": title or f"{platform.capitalize()} Download",
            "author": author,
            "thumbnail": thumbnail,
            "media_type": media_type,
            "items": items
        }


async def extract_media(url: str) -> Dict[str, Any]:
    """Unified entry point for media extraction across all platforms."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    platform = detect_platform(url)

    # 1. Fast Reddit JSON extraction
    if platform == "reddit":
        direct_reddit = await extract_reddit_direct(url)
        if direct_reddit and direct_reddit.get("items"):
            return direct_reddit

    # 2. Specialized Instagram Extractor
    if platform == "instagram":
        try:
            return extract_instagram(url)
        except Exception:
            # Direct fallback for Instagram photos/carousels
            fallback = await extract_instagram_fallback(url)
            if fallback and fallback.get("items"):
                return fallback

    # 3. Universal yt-dlp extraction for all other platforms
    try:
        return extract_with_ytdlp(url, platform)
    except Exception as e:
        err_msg = str(e)
        if "No video formats found" in err_msg and platform == "instagram":
            fallback = await extract_instagram_fallback(url)
            if fallback and fallback.get("items"):
                return fallback
        if "Private" in err_msg or "login" in err_msg.lower():
            raise ValueError("This post appears to be private or requires a login.")
        raise ValueError(f"Failed to extract media: {err_msg}")
