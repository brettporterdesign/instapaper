#!/usr/bin/env python3
"""
Fetch SBS World News articles from their RSS feed and push any new ones
to Instapaper.

Requires:
    INSTAPAPER_USERNAME    - your Instapaper login email
    INSTAPAPER_PASSWORD    - your Instapaper login password

No API key needed - this is a plain public RSS feed.

Includes the same XML sanitisation used for other feeds (fixing stray
unescaped ampersands and invalid control characters), since real-world
RSS feeds occasionally contain small formatting issues that break
strict XML parsing otherwise.

Keeps a small JSON file (sbs_seen.json) of article URLs already sent,
so the same article isn't saved twice. GitHub Actions commits this
file back to the repo after each run so state persists between
scheduled runs.
"""

import json
import os
import re
import sys
from pathlib import Path

import feedparser
import requests
from requests.auth import HTTPBasicAuth

# --- Config -----------------------------------------------------------

SBS_FEED_URL = "https://www.sbs.com.au/news/topic/world/feed"

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

INSTAPAPER_ADD_URL = "https://www.instapaper.com/api/add"

SEEN_FILE = Path(__file__).parent / "sbs_seen.json"
MAX_SEEN_ENTRIES = 500

_BARE_AMPERSAND_RE = re.compile(r"&(?!#\d+;|#x[0-9a-fA-F]+;|[a-zA-Z][a-zA-Z0-9]*;)")
_INVALID_XML_CHARS_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

# --- Helpers ------------------------------------------------------------

def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def save_seen(seen: set) -> None:
    trimmed = list(seen)[-MAX_SEEN_ENTRIES:]
    SEEN_FILE.write_text(json.dumps(trimmed, indent=2))


def sanitize_feed_xml(raw_bytes: bytes) -> bytes:
    text = raw_bytes.decode("utf-8", errors="replace")
    text = _BARE_AMPERSAND_RE.sub("&amp;", text)
    text = _INVALID_XML_CHARS_RE.sub("", text)
    return text.encode("utf-8")


def fetch_articles() -> list:
    resp = requests.get(SBS_FEED_URL, headers=REQUEST_HEADERS, timeout=30)
    print(f"Feed request status: {resp.status_code}, {len(resp.content)} bytes received")

    cleaned_content = sanitize_feed_xml(resp.content)

    parsed = feedparser.parse(cleaned_content)
    if parsed.bozo:
        print(f"Feed parsing warning (non-fatal): {parsed.bozo_exception}", file=sys.stderr)

    print(f"Feed entries found: {len(parsed.entries)}")

    articles = []
    for entry in parsed.entries:
        url = entry.get("link")
        title = entry.get("title", "Untitled")
        if url:
            articles.append({"url": url, "title": title})
    return articles


def save_to_instapaper(url: str, title: str, username: str, password: str) -> None:
    payload = {"url": url, "title": title}
    resp = requests.post(
        INSTAPAPER_ADD_URL,
        data=payload,
        auth=HTTPBasicAuth(username, password),
        timeout=30,
    )
    if resp.status_code != 201:
        raise RuntimeError(
            f"Instapaper add failed ({resp.status_code}): {resp.text[:200]} "
            f"for {url}"
        )


def main() -> int:
    ip_user = os.environ.get("INSTAPAPER_USERNAME")
    ip_pass = os.environ.get("INSTAPAPER_PASSWORD")

    missing = [
        name
        for name, val in (
            ("INSTAPAPER_USERNAME", ip_user),
            ("INSTAPAPER_PASSWORD", ip_pass),
        )
        if not val
    ]
    if missing:
        print(f"Missing required environment variables: {', '.join(missing)}", file=sys.stderr)
        return 1

    seen = load_seen()
    articles = fetch_articles()

    new_count = 0
    for article in articles:
        url = article["url"]
        title = article["title"]
        if url in seen:
            continue

        try:
            save_to_instapaper(url, title, ip_user, ip_pass)
            print(f"Saved: {title}")
            seen.add(url)
            new_count += 1
        except Exception as exc:
            print(f"Failed to save '{title}': {exc}", file=sys.stderr)

    save_seen(seen)
    print(f"Done. {new_count} new article(s) saved to Instapaper.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
