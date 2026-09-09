#!/usr/bin/env python3
"""
Fetch ABC News Australia articles from the "Top Stories" and "Just In"
RSS feeds, merge them, and push any new ones to Instapaper.

Since both feeds draw from the same pool of ABC articles, a story can
appear in both. Both feeds are merged and checked against a single
shared "seen" list, so an article that appears in both feeds is only
ever saved to Instapaper once.

Requires:
    INSTAPAPER_USERNAME    - your Instapaper login email
    INSTAPAPER_PASSWORD    - your Instapaper login password

No API key needed for ABC - these are plain public RSS feeds.

Keeps a small JSON file (abc_seen.json) of article URLs already sent, so
the same article isn't saved twice. GitHub Actions commits this file
back to the repo after each run so state persists between scheduled
runs.
"""

import json
import os
import sys
from pathlib import Path

import feedparser
import requests
from requests.auth import HTTPBasicAuth

# --- Config -----------------------------------------------------------

ABC_FEEDS = {
    "Top Stories": "https://www.abc.net.au/news/feed/10719986/rss.xml",
    "Just In": "https://www.abc.net.au/news/feed/10719976/rss.xml",
}

INSTAPAPER_ADD_URL = "https://www.instapaper.com/api/add"

SEEN_FILE = Path(__file__).parent / "abc_seen.json"
MAX_SEEN_ENTRIES = 500

# --- Helpers ------------------------------------------------------------

def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def save_seen(seen: set) -> None:
    trimmed = list(seen)[-MAX_SEEN_ENTRIES:]
    SEEN_FILE.write_text(json.dumps(trimmed, indent=2))


def fetch_feed_articles(feed_url: str) -> list:
    parsed = feedparser.parse(feed_url)
    articles = []
    for entry in parsed.entries:
        url = entry.get("link")
        title = entry.get("title", "Untitled")
        if url:
            articles.append({"url": url, "title": title})
    return articles


def fetch_all_articles() -> list:
    """Fetch and merge articles from every configured ABC feed."""
    all_articles = []
    seen_urls_this_run = set()
    for feed_name, feed_url in ABC_FEEDS.items():
        for article in fetch_feed_articles(feed_url):
            # Skip within-this-run duplicates (e.g. same story in both feeds)
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
