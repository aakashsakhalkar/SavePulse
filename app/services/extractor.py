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
            description = post_data.get("selftext") or title
            return {
                "platform": "reddit",
                "title": title,
                "author": f"u/{author}",
                "author_id": f"u/{author}",
                "description": description,
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
                    "author": "@instagram_creator",
                    "author_id": "@instagram_creator",
                    "description": "Public media post from Instagram.",
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
    
    # Harvester for highest resolution thumbnail
    thumbnail = info.get("thumbnail") or ""
    thumbnails = info.get("thumbnails") or []
    if thumbnails:
        thumbnail = thumbnails[-1].get("url") or thumbnail

    items: List[Dict[str, Any]] = []

    # Check if this is a carousel with multiple entries
    entries = info.get("entries")
    if entries:
        entries_iter = iter(entries)
        idx = 1
        while True:
            try:
                entry = next(entries_iter)
            except StopIteration:
                break
            except Exception:
                idx += 1
                continue

            if not entry:
                idx += 1
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
                thumb = entry.get("thumbnail") or (entry_thumbnails[-1]["url"] if entry_thumbnails else "") or thumbnail
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

            idx += 1

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
                    "id": f"video_{fmt.get('format_id', 'hd')}",
                    "type": "video",
                    "quality": f"{height}p (MP4)",
                    "ext": "mp4",
                    "url": fmt_url,
                    "height": height,
                    "thumbnail": thumbnail,
                    "filesize_str": format_filesize(fmt.get("filesize") or fmt.get("filesize_approx"))
                })

        if video_formats:
            # Sort descending and deduplicate identical resolutions
            video_formats.sort(key=lambda x: x.get("height", 0), reverse=True)
            seen_resolutions = set()
            for v_fmt in video_formats:
                q = v_fmt["quality"]
                if q not in seen_resolutions:
                    seen_resolutions.add(q)
                    items.append({
                        "id": v_fmt["id"],
                        "type": "video",
                        "quality": v_fmt["quality"],
                        "ext": "mp4",
                        "url": v_fmt["url"],
                        "thumbnail": thumbnail,
                        "filesize_str": v_fmt["filesize_str"]
                    })
                if len(items) >= 3:
                    break

            # Fallback if formats lacked vcodec tags
            if not items and info.get("url"):
                items.append({
                    "id": "single_video_best",
                    "type": "video",
                    "quality": "Best Quality (HD)",
                    "ext": "mp4",
                    "url": info["url"],
                    "thumbnail": thumbnail,
                    "filesize_str": format_filesize(info.get("filesize"))
                })
        else:
            # Single photo post
            img_url = (thumbnails[-1]["url"] if thumbnails else "") or info.get("url")
            if img_url:
                items.append({
                    "id": "single_photo",
                    "type": "image",
                    "quality": "Original Photo (Full HD)",
                    "ext": "jpg",
                    "url": img_url,
                    "thumbnail": img_url,
                    "filesize_str": "Original"
                })
                if not thumbnail:
                    thumbnail = img_url

    if not items:
        raise ValueError("No media items extracted.")

    # Strictly assign media_type: only multi-item albums become "gallery"
    if entries and len(items) > 1:
        media_type = "gallery"
    elif any(i.get("type") == "video" for i in items):
        media_type = "video"
    else:
        media_type = "image"

    description = info.get("description") or info.get("title") or "Instagram media post."
    author_id = f"@{info.get('uploader_id')}" if info.get('uploader_id') and not str(info.get('uploader_id')).startswith('@') else (info.get('uploader_id') or author)

    return {
        "platform": "instagram",
        "title": title,
        "author": author,
        "author_id": author_id,
        "description": description,
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

        author = info.get("uploader") or info.get("channel") or info.get("uploader_id") or f"{platform.capitalize()} Creator"
        author_id = f"@{info.get('uploader_id')}" if info.get('uploader_id') and not str(info.get('uploader_id')).startswith('@') else (info.get('uploader_id') or author)
        description = info.get("description") or info.get("title") or f"Public post from {platform.capitalize()}."
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
                    "thumbnail": entry_thumb or thumbnail,
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
                        "thumbnail": thumbnail,
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
                        "thumbnail": thumbnail,
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
                    "thumbnail": thumbnail,
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
            "author_id": author_id,
            "description": description,
            "thumbnail": thumbnail,
            "media_type": media_type,
            "items": items
        }


def is_profile_url(url: str, platform: str) -> bool:
    """Detect if URL points to a user profile / channel instead of a specific media post."""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        return False
    parts = path.split("/")
    
    if platform == "instagram":
        if parts[0] in ["p", "reel", "reels", "tv", "stories", "explore", "direct", "accounts", "developer", "about"]:
            return False
        return len(parts) == 1 and bool(parts[0])

    elif platform == "tiktok":
        return parts[0].startswith("@") and len(parts) == 1

    elif platform == "twitter":
        if parts[0] in ["status", "i", "home", "explore", "messages", "search", "notifications", "settings"]:
            return False
        return len(parts) == 1 and bool(parts[0])

    elif platform == "youtube":
        if parts[0].startswith("@") and len(parts) == 1:
            return True
        if parts[0] in ["channel", "c", "user"] and len(parts) >= 2:
            return True
        return False

    elif platform == "reddit":
        return parts[0] in ["user", "u"] and len(parts) >= 2

    elif platform == "pinterest":
        if parts[0] in ["pin", "search", "ideas", "today"]:
            return False
        return len(parts) == 1 and bool(parts[0])

    return False


async def extract_profile_picture(url: str, platform: str) -> Optional[Dict[str, Any]]:
    """Extract HD profile picture (avatar / DP) for public accounts."""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.strip("/")
    parts = path.split("/")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/json,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        # 1. Instagram Profile Picture
        if platform == "instagram":
            username = parts[0].lstrip("@")
            ig_api_url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
            ig_headers = {
                **headers,
                "X-IG-App-ID": "936619743392459",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"https://www.instagram.com/{username}/"
            }
            dp_url = None
            full_name = username
            followers_str = ""

            try:
                async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                    resp = await client.get(ig_api_url, headers=ig_headers)
                    if resp.status_code == 200:
                        user_data = resp.json().get("data", {}).get("user", {})
                        if user_data:
                            hd_info = user_data.get("hd_profile_pic_url_info") or {}
                            dp_url = hd_info.get("url") or user_data.get("profile_pic_url_hd") or user_data.get("profile_pic_url")
                            full_name = user_data.get("full_name") or username
                            followers = user_data.get("edge_followed_by", {}).get("count", 0)
                            if followers:
                                followers_str = f"{followers:,} Followers"
            except Exception:
                pass

            # Fallback to HTML scrape
            if not dp_url:
                async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                    resp = await client.get(f"https://www.instagram.com/{username}/", headers=headers)
                    if resp.status_code == 200:
                        m = re.search(r'<meta property="og:image" content="([^"]+)"', resp.text)
                        if m:
                            dp_url = html.unescape(m.group(1))

            if dp_url:
                title = f"{full_name} (@{username}) • Instagram Profile Picture"
                if followers_str:
                    title += f" • {followers_str}"
                return {
                    "platform": "instagram",
                    "title": title,
                    "author": full_name or f"@{username}",
                    "author_id": f"@{username}",
                    "description": f"Instagram Profile of {full_name} (@{username}). {followers_str}",
                    "thumbnail": dp_url,
                    "media_type": "image",
                    "items": [{
                        "id": "ig_hd_dp",
                        "type": "image",
                        "quality": "HD Profile Picture (Original)",
                        "ext": "jpg",
                        "url": dp_url,
                        "filesize_str": "Full HD"
                    }]
                }

        # 2. Twitter / X Profile Picture
        elif platform == "twitter":
            username = parts[0].lstrip("@")
            dp_url = None
            title = f"@{username} • X Profile Picture"
            name = username
            
            try:
                async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                    resp = await client.get(f"https://api.vxtwitter.com/{username}", headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        dp_url = data.get("avatar_url") or data.get("user_profile_image_url")
                        if dp_url:
                            dp_url = dp_url.replace("_normal.", "_400x400.")
                        name = data.get("user_name") or username
                        title = f"{name} (@{username}) • X Profile Picture"
            except Exception:
                pass

            if not dp_url:
                async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                    resp = await client.get(f"https://x.com/{username}", headers=headers)
                    if resp.status_code == 200:
                        m = re.search(r'<meta property="og:image" content="([^"]+)"', resp.text)
                        if m:
                            dp_url = html.unescape(m.group(1)).replace("_normal.", "_400x400.")

            if dp_url:
                return {
                    "platform": "twitter",
                    "title": title,
                    "author": name or f"@{username}",
                    "author_id": f"@{username}",
                    "description": f"X (Twitter) Profile Picture for {name} (@{username}).",
                    "thumbnail": dp_url,
                    "media_type": "image",
                    "items": [{
                        "id": "twitter_hd_dp",
                        "type": "image",
                        "quality": "HD Profile Picture (400x400)",
                        "ext": "jpg",
                        "url": dp_url,
                        "filesize_str": "HD"
                    }]
                }

        # 3. YouTube Channel Avatar
        elif platform == "youtube":
            clean_url = url.split("?")[0]
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(clean_url, headers=headers)
                if resp.status_code == 200:
                    og_match = re.search(r'<meta property="og:image" content="([^"]+)"', resp.text)
                    title_match = re.search(r'<meta property="og:title" content="([^"]+)"', resp.text)
                    
                    dp_url = og_match.group(1) if og_match else None
                    ch_title = title_match.group(1) if title_match else "YouTube Channel"
                    
                    if dp_url:
                        dp_hd = re.sub(r'=s\d+-[^\"]+', '=s800-c-k-c0x00ffffff-no-rj', dp_url)
                        return {
                            "platform": "youtube",
                            "title": f"{ch_title} • YouTube Avatar",
                            "author": ch_title,
                            "author_id": ch_title,
                            "description": f"Official YouTube Channel Avatar for {ch_title}.",
                            "thumbnail": dp_hd,
                            "media_type": "image",
                            "items": [{
                                "id": "yt_channel_dp",
                                "type": "image",
                                "quality": "HD Channel Avatar (800x800)",
                                "ext": "jpg",
                                "url": dp_hd,
                                "filesize_str": "Full HD"
                            }]
                        }

        # 4. Reddit User Profile Picture
        elif platform == "reddit":
            username = parts[1] if parts[0] in ["user", "u"] else parts[0]
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                r_headers = {**headers, "User-Agent": "SavePulse/2.0 (by u/SavePulseTeam)"}
                resp = await client.get(f"https://www.reddit.com/user/{username}/about.json", headers=r_headers)
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    icon = data.get("icon_img") or data.get("snoovatar_img")
                    if icon:
                        clean_icon = icon.split("?")[0]
                        return {
                            "platform": "reddit",
                            "title": f"u/{username} • Reddit Profile Avatar",
                            "author": f"u/{username}",
                            "author_id": f"u/{username}",
                            "description": f"Reddit Avatar for u/{username}.",
                            "thumbnail": clean_icon,
                            "media_type": "image",
                            "items": [{
                                "id": "reddit_dp",
                                "type": "image",
                                "quality": "Reddit Avatar (Original)",
                                "ext": "png" if clean_icon.endswith(".png") else "jpg",
                                "url": clean_icon,
                                "filesize_str": "Original"
                            }]
                        }

        # 5. TikTok Profile Picture
        elif platform == "tiktok":
            username = parts[0]
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(f"https://www.tiktok.com/{username}", headers=headers)
                if resp.status_code == 200:
                    og_match = re.search(r'<meta property="og:image" content="([^"]+)"', resp.text)
                    if og_match:
                        dp_url = html.unescape(og_match.group(1))
                        return {
                            "platform": "tiktok",
                            "title": f"{username} • TikTok Profile Picture",
                            "author": username,
                            "author_id": username,
                            "description": f"TikTok Profile Picture for {username}.",
                            "thumbnail": dp_url,
                            "media_type": "image",
                            "items": [{
                                "id": "tiktok_hd_dp",
                                "type": "image",
                                "quality": "HD Profile Picture",
                                "ext": "jpg",
                                "url": dp_url,
                                "filesize_str": "HD"
                            }]
                        }

        # 6. Pinterest Profile Picture
        elif platform == "pinterest":
            username = parts[0]
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(f"https://www.pinterest.com/{username}/", headers=headers)
                if resp.status_code == 200:
                    og_match = re.search(r'<meta property="og:image" content="([^"]+)"', resp.text)
                    pinimg_match = re.search(r'https://i\.pinimg\.com/(?:originals|\d+x)/[a-zA-Z0-9/_\-]+\.(?:png|jpg|jpeg)', resp.text)
                    dp_url = None
                    if og_match:
                        dp_url = html.unescape(og_match.group(1))
                        dp_url = dp_url.replace("/150x150/", "/736x/").replace("/280x280/", "/736x/")
                    elif pinimg_match:
                        dp_url = pinimg_match.group(0)

                    if dp_url:
                        return {
                            "platform": "pinterest",
                            "title": f"{username} • Pinterest Profile Picture",
                            "author": username,
                            "author_id": username,
                            "description": f"Pinterest Profile Picture for {username}.",
                            "thumbnail": dp_url,
                            "media_type": "image",
                            "items": [{
                                "id": "pinterest_hd_dp",
                                "type": "image",
                                "quality": "HD Profile Picture",
                                "ext": "jpg",
                                "url": dp_url,
                                "filesize_str": "Full HD"
                            }]
                        }

    except Exception:
        pass

    return None


async def extract_media(url: str) -> Dict[str, Any]:
    """Unified entry point for media extraction across all platforms."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    platform = detect_platform(url)

    # 0. Profile Picture / Avatar extraction
    if is_profile_url(url, platform):
        dp_result = await extract_profile_picture(url, platform)
        if dp_result and dp_result.get("items"):
            return dp_result

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
            raise ValueError("This post or profile appears to be private or requires a login.")
        raise ValueError(f"Failed to extract media: {err_msg}")
