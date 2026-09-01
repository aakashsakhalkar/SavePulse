import asyncio
import sys
from app.services.extractor import extract_media, detect_platform

async def test_extraction():
    test_urls = [
        # Test 1: Reddit public post
        "https://www.reddit.com/r/NatureIsFuckingLit/comments/18x9k3j/aurora_borealis_over_norway/",
        # Test 2: Platform detection
        "https://www.instagram.com/reel/C123456789/",
        "https://twitter.com/NASA/status/1744410982390231289",
        "https://www.facebook.com/watch/?v=123456789"
    ]
    
    print("=== Testing Platform Detection ===")
    for u in test_urls:
        print(f"URL: {u} -> Detected: {detect_platform(u)}")

    print("\n=== Testing Reddit JSON Extractor ===")
    try:
        data = await extract_media("https://www.reddit.com/r/pics/comments/16uox10/a_photo_i_took_in_switzerland/")
        print("Success! Extracted metadata:")
        print(f"Title: {data.get('title')}")
        print(f"Platform: {data.get('platform')}")
        print(f"Media Type: {data.get('media_type')}")
        print(f"Downloadable items count: {len(data.get('items', []))}")
        for item in data.get("items", []):
            print(f"  - [{item.get('type')}] {item.get('quality')}: {item.get('url')[:60]}...")
    except Exception as e:
        print(f"Test Reddit extraction error (expected if network is blocked or post removed): {e}")

if __name__ == "__main__":
    asyncio.run(test_extraction())
