#!/usr/bin/env python3
"""
Fetch articles from multiple BBC News RSS feeds, merge them, and push
any new ones to Instapaper.

Since the same story can appear across several BBC feeds (e.g. a big
tech story showing up in both Top Stories and Technology), all
configured feeds are merged and checked against a single shared
"seen" list, so any article is only ever saved to Instapaper once,
regardless of how many feeds it appeared in.

Requires:
    INSTAPAPER_USERNAME    - your Instapaper login email
    INSTAPAPER_PASSWORD    - your Instapaper login password

No API key needed - these are BBC's plain public RSS feeds.

Includes XML sanitisation (fixing stray unescaped ampersands and
invalid control characters) as a safety net, since real-world RSS
feeds occasionally contain small formatting issues that break strict
XML parsing otherwise.

Keeps a small JSON file (bbc_seen.json) of article URLs already sent,
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

BBC_FEEDS = {
    "Top Stories": "http://feeds.bbci.co.uk/news/rss.xml",
    "World": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "Politics": "http://feeds.bbci.co.uk/news/politics/rss.xml",
    "Technology": "http://feeds.bbci.co.uk/news/technology/rss.xml",
    "Science & Environment": "http://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
    "Entertainment & Arts": "http://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
}

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

INSTAPAPER_ADD_URL = "https://www.instapaper.com/api/add"

SEEN_FILE = Path(__file__).parent / "bbc_seen.json"
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


def fetch_feed_articles(feed_name: str, feed_url: str) -> list:
    resp = requests.get(feed_url, headers=REQUEST_HEADERS, timeout=30)
    cleaned_content = sanitize_feed_xml(resp.content)
    parsed = feedparser.parse(cleaned_content)

    if parsed.bozo:
        print(f"[{feed_name}] parsing warning (non-fatal): {parsed.bozo_exception}", file=sys.stderr)

    articles = []
    for entry in parsed.entries:
        url = entry.get("link")
        title = entry.get("title", "Untitled")
        if url:
            articles.append({"url": url, "title": title})

    print(f"[{feed_name}] {len(articles)} entries found")
    return articles


def fetch_all_articles() -> list:
    """Fetch and merge articles from every configured BBC feed, deduping within this run."""
    all_articles = []
    seen_urls_this_run = set()

    for feed_name, feed_url in BBC_FEEDS.items():
        for article in fetch_feed_articles(feed_name, feed_url):
            if article["url"] in seen_urls_this_run:
                continue
            seen_urls_this_run.add(article["url"])
            all_articles.append(article)

    return all_articles


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
    articles = fetch_all_articles()

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
