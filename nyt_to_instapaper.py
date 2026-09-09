#!/usr/bin/env python3
"""
Fetch trending New York Times articles and push any new ones to Instapaper.

Requires three environment variables (set as GitHub Actions secrets, or
export them locally for testing):
    NYT_API_KEY            - free key from developer.nytimes.com
    INSTAPAPER_USERNAME    - your Instapaper login email
    INSTAPAPER_PASSWORD    - your Instapaper login password

Keeps a small JSON file (seen.json) of article URLs already sent, so the
same article isn't saved twice. GitHub Actions commits this file back to
the repo after each run so state persists between scheduled runs.
"""

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlencode

import requests
from requests.auth import HTTPBasicAuth

# --- Config -----------------------------------------------------------

# NYT "Most Popular" endpoint. Options: viewed, emailed, shared.
# "viewed" over the last day is the closest free equivalent to "trending".
NYT_PERIOD_DAYS = 1
NYT_METRIC = "viewed"  # viewed | emailed | shared
NYT_URL = f"https://api.nytimes.com/svc/mostpopular/v2/{NYT_METRIC}/{NYT_PERIOD_DAYS}.json"

INSTAPAPER_ADD_URL = "https://www.instapaper.com/api/add"

SEEN_FILE = Path(__file__).parent / "seen.json"
MAX_SEEN_ENTRIES = 500  # keep the state file from growing forever

# --- Helpers ------------------------------------------------------------

def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def save_seen(seen: set) -> None:
    # Keep only the most recent MAX_SEEN_ENTRIES to bound file size.
    trimmed = list(seen)[-MAX_SEEN_ENTRIES:]
    SEEN_FILE.write_text(json.dumps(trimmed, indent=2))


def fetch_trending_articles(api_key: str) -> list:
    resp = requests.get(NYT_URL, params={"api-key": api_key}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("results", [])


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
    api_key = os.environ.get("NYT_API_KEY")
    ip_user = os.environ.get("INSTAPAPER_USERNAME")
    ip_pass = os.environ.get("INSTAPAPER_PASSWORD")

    missing = [
        name
        for name, val in (
            ("NYT_API_KEY", api_key),
            ("INSTAPAPER_USERNAME", ip_user),
            ("INSTAPAPER_PASSWORD", ip_pass),
        )
        if not val
    ]
    if missing:
        print(f"Missing required environment variables: {', '.join(missing)}", file=sys.stderr)
        return 1

    seen = load_seen()
    articles = fetch_trending_articles(api_key)

    new_count = 0
    for article in articles:
        url = article.get("url")
        title = article.get("title", "Untitled")
        if not url or url in seen:
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
