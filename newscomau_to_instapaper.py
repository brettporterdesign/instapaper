#!/usr/bin/env python3
"""
Fetch news.com.au's latest news RSS feed and push any new articles to
Instapaper.

Requires:
    INSTAPAPER_USERNAME    - your Instapaper login email
    INSTAPAPER_PASSWORD    - your Instapaper login password

No API key needed - this is a plain public RSS feed.

Note: news.com.au runs a partial paywall (some articles are tagged as
subscriber-only "Plus" content). Those specific articles may fail to
parse in Instapaper the same way NYT paywalled articles do, since
Instapaper's fetcher has no login session. Most news.com.au content is
free, so this should affect a minority of articles rather than all of
them.

Keeps a small JSON file (newscomau_seen.json) of article URLs already
sent, so the same article isn't saved twice. GitHub Actions commits
this file back to the repo after each run so state persists between
scheduled runs.
"""

import json
import os
import sys
from pathlib import Path

import feedparser
import requests
from requests.auth import HTTPBasicAuth

# --- Config -----------------------------------------------------------

NEWSCOMAU_FEED_URL = "https://www.news.com.au/content-feeds/latest-news-rss/"

INSTAPAPER_ADD_URL = "https://www.instapaper.com/api/add"

SEEN_FILE = Path(__file__).parent / "newscomau_seen.json"
MAX_SEEN_ENTRIES = 500

# --- Helpers ------------------------------------------------------------

def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def save_seen(seen: set) -> None:
    trimmed = list(seen)[-MAX_SEEN_ENTRIES:]
    SEEN_FILE.write_text(json.dumps(trimmed, indent=2))


def fetch_articles() -> list:
    parsed = feedparser.parse(NEWSCOMAU_FEED_URL)
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
