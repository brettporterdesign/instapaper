#!/usr/bin/env python3
"""
Fetch the latest Guardian Australia articles (general + technology) and
push any new ones to Instapaper.

Pulls from two Guardian Open Platform queries and merges them:
  - Latest articles, production office = Australia
  - Latest articles, production office = Australia, section = technology

Since a technology story can also show up in the general Australia
feed, both queries are merged and checked against a single shared
"seen" list, so an article that appears in both is only ever saved to
Instapaper once.

Requires:
    GUARDIAN_API_KEY       - free key from open-platform.theguardian.com/access
    INSTAPAPER_USERNAME    - your Instapaper login email
    INSTAPAPER_PASSWORD    - your Instapaper login password

Keeps a small JSON file (guardian_seen.json) of article URLs already sent, so
the same article isn't saved twice. GitHub Actions commits this file back to
the repo after each run so state persists between scheduled runs.
"""

import json
import os
import sys
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

# --- Config -----------------------------------------------------------

GUARDIAN_SEARCH_URL = "https://content.guardianapis.com/search"

# General Guardian Australia latest news.
GUARDIAN_GENERAL_PARAMS = {
    "production-office": "aus",
    "order-by": "newest",
    "page-size": 20,
}

# Guardian, scoped to the technology section (global, not limited to
# the Australia production office - tech coverage there is fairly light).
GUARDIAN_TECH_PARAMS = {
    "section": "technology",
    "order-by": "newest",
    "page-size": 20,
}

INSTAPAPER_ADD_URL = "https://www.instapaper.com/api/add"

SEEN_FILE = Path(__file__).parent / "guardian_seen.json"
MAX_SEEN_ENTRIES = 500

# --- Helpers ------------------------------------------------------------

def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def save_seen(seen: set) -> None:
    trimmed = list(seen)[-MAX_SEEN_ENTRIES:]
    SEEN_FILE.write_text(json.dumps(trimmed, indent=2))


def fetch_articles(api_key: str, extra_params: dict) -> list:
    params = dict(extra_params)
    params["api-key"] = api_key
    resp = requests.get(GUARDIAN_SEARCH_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    articles = []
    for item in data.get("response", {}).get("results", []):
        url = item.get("webUrl")
        title = item.get("webTitle", "Untitled")
        if url:
            articles.append({"url": url, "title": title})
    return articles


def fetch_all_articles(api_key: str) -> list:
    """Fetch and merge articles from both Guardian queries, deduping within this run."""
    all_articles = []
    seen_urls_this_run = set()

    for params in (GUARDIAN_GENERAL_PARAMS, GUARDIAN_TECH_PARAMS):
        for article in fetch_articles(api_key, params):
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
    api_key = os.environ.get("GUARDIAN_API_KEY")
    ip_user = os.environ.get("INSTAPAPER_USERNAME")
    ip_pass = os.environ.get("INSTAPAPER_PASSWORD")

    missing = [
        name
        for name, val in (
            ("GUARDIAN_API_KEY", api_key),
            ("INSTAPAPER_USERNAME", ip_user),
            ("INSTAPAPER_PASSWORD", ip_pass),
        )
        if not val
    ]
    if missing:
        print(f"Missing required environment variables: {', '.join(missing)}", file=sys.stderr)
        return 1

    seen = load_seen()
    articles = fetch_all_articles(api_key)

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
