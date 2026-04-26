from urllib.parse import urlencode
import xml.etree.ElementTree as ET
import re
import json
import os
import time
from datetime import datetime, timezone

import requests
from playwright.sync_api import sync_playwright


BRIDGES = [
    "https://rss-bridge.org/bridge01/",
    "https://bridge.hostux.net/",
    "https://tools.bheil.net/rss-bridge",
    "https://rss-bridge.snopyta.org/",
]

NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
]

KEYWORDS = [
    "review",
    "hands-on",
    "first look",
    "unboxing",
    "impressions",
    "tested",
    "benchmark",
    "battery",
    "battery life",
    "charging",
    "fast charging",
    "wireless charging",
    "camera",
    "low light",
    "zoom",
    "portrait mode",
    "night mode",
    "video quality",
    "stabilization",
    "smartphone",
    "phone",
    "android",
    "iphone",
    "pixel",
    "galaxy",
    "foldable",
    "tablet",
    "ipad",
    "stylus",
    "laptop",
    "notebook",
    "ultrabook",
    "macbook",
    "chromebook",
    "2-in-1",
    "desktop",
    "mini pc",
    "workstation",
    "monitor",
    "oled",
    "qled",
    "mini led",
    "refresh rate",
    "hdr",
    "gaming monitor",
    "cpu",
    "processor",
    "chip",
    "soc",
    "gpu",
    "graphics card",
    "rtx",
    "radeon",
    "npu",
    "ai pc",
    "ram",
    "ddr5",
    "ssd",
    "nvme",
    "storage",
    "motherboard",
    "pc build",
    "gaming pc",
    "console",
    "playstation",
    "xbox",
    "nintendo switch",
    "steam deck",
    "vr",
    "ar",
    "mixed reality",
    "headset",
    "earbuds",
    "headphones",
    "smartwatch",
    "fitness tracker",
    "wearable",
    "router",
    "wifi 6",
    "wifi 7",
    "mesh",
    "bluetooth",
    "usb-c",
    "thunderbolt",
    "smart home",
    "smart speaker",
    "smart display",
    "robot vacuum",
    "security camera",
    "doorbell",
    "ev",
    "electric vehicle",
    "tesla",
    "autopilot",
    "self-driving",
    "driver assistance",
    "drone",
    "action camera",
    "gopro",
    "3d printer",
]
RETURN_ALL_IF_NO_KEYWORD_MATCH = False

IMAGE_URL_PATTERNS = (
    "pbs.twimg.com/media/",
    "pbs.twimg.com/tweet_video_thumb/",
    "pbs.twimg.com/amplify_video_thumb/",
    "pbs.twimg.com/ext_tw_video_thumb/",
)

MAX_SCROLLS = 12
SCROLL_DELAY_SECONDS = 1.0
COMMENTS_PER_POST = 5

INFLUENCER = "elonmusk"
TOP_TECH_INFLUENCERS = [
    "MKBHD",
    "LinusTech",
    "UnboxTherapy",
    "Mrwhosetheboss",
    "iJustine",
    "Dave2D",
    "AustinEvans",
    "SnazzyLabs",
    "TechLinked",
    "elonmusk",
]


def _build_bridge_url(bridge_url, username):
    base_url = bridge_url.rstrip("/") + "/"
    query = urlencode(
        {
            "action": "display",
            "bridge": "TwitterBridge",
            "context": "By username",
            "u": username,
            "format": "Json",
        }
    )
    return f"{base_url}?{query}"


def fetch_with_failover(username, bridges=None, timeout=10):
    bridge_list = bridges or BRIDGES
    for bridge in bridge_list:
        try:
            url = _build_bridge_url(bridge, username)
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            print(f"Success using {bridge}")
            return response.json()
        except requests.RequestException as exc:
            print(f"Bridge {bridge} failed: {exc}")
            continue
    return None


def _build_nitter_rss_url(instance_url, username):
    clean_instance = instance_url.rstrip("/")
    clean_username = username.lstrip("@")
    return f"{clean_instance}/{clean_username}/rss"


def _parse_nitter_rss(xml_text, username):
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    if channel is None:
        return []

    tweets = []
    for item in channel.findall("item"):
        content = (item.findtext("description") or "").strip()
        if not content:
            content = (item.findtext("title") or "").strip()

        tweet_data = {
            "id": (item.findtext("guid") or item.findtext("link") or "").strip(),
            "url": (item.findtext("link") or "").strip(),
            "content": content,
            "date": (item.findtext("pubDate") or "").strip(),
            "author": username,
        }
        tweets.append(tweet_data)

    return tweets


def fetch_from_nitter(username, instances=None, timeout=10):
    nitter_instances = instances or NITTER_INSTANCES
    for instance in nitter_instances:
        try:
            url = _build_nitter_rss_url(instance, username)
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            tweets = _parse_nitter_rss(response.text, username)
            if tweets:
                print(f"Success using Nitter RSS {instance}")
                return {"items": tweets}
        except (requests.RequestException, ET.ParseError) as exc:
            print(f"Nitter instance {instance} failed: {exc}")
            continue
    return None


def _parse_jina_x_timeline(markdown_text, username):
    lines = markdown_text.splitlines()
    tweets = []
    seen_ids = set()

    for idx, line in enumerate(lines):
        if "/status/" not in line or "/analytics" in line:
            continue

        url_match = re.search(r"\((https?://x\.com/[^)]+/status/(\d+)[^)]*)\)", line)
        if not url_match:
            continue

        tweet_id = url_match.group(2)
        if tweet_id in seen_ids:
            continue

        date_match = re.search(r"\[([^\]]+)\]\(https?://x\.com/", line)
        date_value = date_match.group(1).strip() if date_match else ""

        content = ""
        block_lines = []
        for next_idx in range(idx + 1, len(lines)):
            candidate = lines[next_idx].strip()
            if candidate and "/status/" in candidate and candidate != line:
                break
            block_lines.append(candidate)

        for candidate in block_lines:
            if not candidate or candidate.startswith("[") or candidate.startswith("#") or candidate == "...":
                continue
            if not content:
                content = candidate

        image_urls = []
        for candidate in block_lines:
            if not candidate:
                continue
            for match in re.finditer(r"https://pbs\.twimg\.com/[^\s)\]]+", candidate):
                matched_url = match.group(0).rstrip(".,;:")
                if any(pattern in matched_url for pattern in IMAGE_URL_PATTERNS):
                    image_urls.append(matched_url)

        image_urls = list(dict.fromkeys(image_urls))

        if not content:
            continue

        seen_ids.add(tweet_id)
        tweets.append(
            {
                "id": tweet_id,
                "url": url_match.group(1),
                "content": content,
                "date": date_value,
                "author": username,
                "image_urls": image_urls,
            }
        )

    return tweets


def fetch_from_jina_x(username, timeout=15):
    clean_username = username.lstrip("@")
    url = f"https://r.jina.ai/http://x.com/{clean_username}"
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        tweets = _parse_jina_x_timeline(response.text, clean_username)
        if tweets:
            print("Success using r.jina.ai X mirror")
            return {"items": tweets}
    except requests.RequestException as exc:
        print(f"r.jina.ai mirror failed: {exc}")
    return None


def _extract_status_id(status_url):
    match = re.search(r"/status/(\d+)", status_url or "")
    return match.group(1) if match else None


def _safe_inner_text(locator):
    try:
        if locator.count() > 0:
            return (locator.first.inner_text() or "").strip()
    except Exception:
        return ""
    return ""


def _extract_tweet_from_card(card, username):
    status_url = None
    for link in card.locator("a[href*='/status/']").all():
        href = link.get_attribute("href")
        if href and "/status/" in href:
            status_url = href if href.startswith("http") else f"https://x.com{href}"
            break

    status_id = _extract_status_id(status_url)
    if not status_id:
        return None

    content = _safe_inner_text(card.locator("div[data-testid='tweetText']"))
    if not content:
        return None

    date_value = ""
    try:
        time_node = card.locator("time").first
        if time_node.count() > 0:
            date_value = time_node.get_attribute("datetime") or ""
    except Exception:
        date_value = ""

    image_urls = []
    for img in card.locator("img").all():
        src = img.get_attribute("src") or ""
        if any(pattern in src for pattern in IMAGE_URL_PATTERNS):
            image_urls.append(src)
    image_urls = list(dict.fromkeys(image_urls))

    return {
        "id": status_id,
        "url": status_url,
        "content": content,
        "date": date_value,
        "author": username,
        "image_urls": image_urls,
    }


def scrape_comments_with_playwright(context, tweet_url, max_comments=COMMENTS_PER_POST):
    comments = []
    page = context.new_page()
    try:
        page.goto(tweet_url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(1200)

        cards = page.locator("article[data-testid='tweet']").all()
        for card in cards[1:]:
            text = _safe_inner_text(card.locator("div[data-testid='tweetText']"))
            if not text:
                continue

            user = ""
            try:
                user = _safe_inner_text(card.locator("div[data-testid='User-Name']"))
            except Exception:
                user = ""

            comments.append({
                "author": user,
                "content": text,
            })
            if len(comments) >= max_comments:
                break
    except Exception:
        pass
    finally:
        page.close()

    return comments


def fetch_with_playwright(username, max_posts=30, with_comments=True):
    clean_username = username.lstrip("@")
    profile_url = f"https://x.com/{clean_username}"
    tweets = []
    seen_ids = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(viewport={"width": 1365, "height": 900})
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        try:
            page.goto(profile_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)

            for _ in range(MAX_SCROLLS):
                cards = page.locator("article[data-testid='tweet']").all()
                for card in cards:
                    tweet = _extract_tweet_from_card(card, clean_username)
                    if not tweet or tweet["id"] in seen_ids:
                        continue

                    if with_comments:
                        tweet["comments"] = scrape_comments_with_playwright(context, tweet["url"])

                    seen_ids.add(tweet["id"])
                    tweets.append(tweet)
                    if len(tweets) >= max_posts:
                        break

                if len(tweets) >= max_posts:
                    break

                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(SCROLL_DELAY_SECONDS)

        finally:
            browser.close()

    return {"items": tweets}


def get_influencer_tweets(username, bridges=None):
    """
    Fetch tweets from RSS-Bridge JSON and keep only review-like posts.
    """
    print(f"Fetching data for @{username}...")

    data = fetch_with_playwright(username, max_posts=30, with_comments=True)
    if not data or not data.get("items"):
        print("Playwright scrape returned no data, trying fallback sources...")
        data = fetch_with_failover(username, bridges=bridges)
    if not data:
        print("RSS-Bridge unavailable, trying Nitter RSS fallbacks...")
        data = fetch_from_nitter(username)
    if not data:
        print("Nitter unavailable, trying r.jina.ai X mirror...")
        data = fetch_from_jina_x(username)
    if not data:
        return []

    all_tweets = []
    matched_tweets = []
    for item in data.get("items", []):
        content = item.get("content_text") or item.get("content") or ""

        author = item.get("author") or {}
        if isinstance(author, dict):
            author_name = author.get("name")
        else:
            author_name = str(author) if author else username

        tweet_data = {
            "id": item.get("id"),
            "url": item.get("url"),
            "content": content,
            "date": item.get("date_published") or item.get("date"),
            "author": author_name,
            "image_urls": item.get("image_urls") or [],
            "comments": item.get("comments") or [],
        }
        all_tweets.append(tweet_data)

        if any(keyword in content.lower() for keyword in KEYWORDS):
            matched_tweets.append(tweet_data)

    if matched_tweets:
        return matched_tweets

    if RETURN_ALL_IF_NO_KEYWORD_MATCH:
        print("No keyword matches found, returning recent posts instead.")
        return all_tweets

    return []


def save_tweets(tweets, username):
    clean_username = username.lstrip("@")
    output_dir = os.path.join("output/tweets/", clean_username)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "tweets.json")

    images_dir = os.path.join(output_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    enriched_tweets = []
    for index, tweet in enumerate(tweets, start=1):
        tweet_copy = dict(tweet)
        downloaded_images = []

        for image_index, image_url in enumerate(tweet.get("image_urls") or [], start=1):
            extension = os.path.splitext(image_url.split("?")[0])[1].lower()
            if extension not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
                extension = ".jpg"

            file_name = f"tweet_{index:03d}_image_{image_index:02d}{extension}"
            image_path = os.path.join(images_dir, file_name)

            try:
                response = requests.get(image_url, timeout=20)
                response.raise_for_status()
                with open(image_path, "wb") as image_handle:
                    image_handle.write(response.content)
                downloaded_images.append(os.path.join("images", file_name))
            except requests.RequestException as exc:
                print(f"Failed to download image for @{username}: {exc}")

        if downloaded_images:
            tweet_copy["image_paths"] = downloaded_images
        enriched_tweets.append(tweet_copy)

    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(enriched_tweets, handle, indent=2, ensure_ascii=False)

    return output_path


def _normalize_influencers(handles):
    normalized = []
    seen = set()
    for handle in handles:
        clean = handle.strip().lstrip("@")
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(clean)
    return normalized


def scrape_top_influencers(handles, max_posts_per_influencer=30):
    influencers = _normalize_influencers(handles)
    aggregate = []
    by_influencer = {}

    for handle in influencers:
        tweets = get_influencer_tweets(handle)
        trimmed = tweets[:max_posts_per_influencer]
        save_tweets(trimmed, handle)

        by_influencer[handle] = {
            "count": len(trimmed),
            "saved_to": os.path.join("output", "tweets", handle, "tweets.json"),
        }

        for tweet in trimmed:
            aggregate.append(
                {
                    "influencer": handle,
                    "id": tweet.get("id"),
                    "url": tweet.get("url"),
                    "content": tweet.get("content"),
                    "date": tweet.get("date"),
                    "author": tweet.get("author"),
                    "image_urls": tweet.get("image_urls") or [],
                    "comments": tweet.get("comments") or [],
                }
            )

    output_dir = os.path.join("output", "tech_trends")
    os.makedirs(output_dir, exist_ok=True)
    dataset_path = os.path.join(output_dir, "tweets_dataset.json")

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "influencers": influencers,
        "keywords": KEYWORDS,
        "total_posts": len(aggregate),
        "per_influencer": by_influencer,
        "posts": aggregate,
    }

    with open(dataset_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)

    return dataset_path, payload


if __name__ == "__main__":
    dataset_path, payload = scrape_top_influencers(TOP_TECH_INFLUENCERS)
    print("\nTop-10 tech influencer scrape complete.")
    print(f"Total posts collected: {payload['total_posts']}")
    print(f"Saved aggregate dataset to {dataset_path}")
    print("\nPer influencer counts:")
    for handle, info in payload["per_influencer"].items():
        print(f"@{handle}: {info['count']} posts")