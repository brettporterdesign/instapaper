# NYT trending → Instapaper (free)

Pushes trending New York Times articles (via NYT's free Most Popular API)
to your Instapaper account automatically, on a schedule, using GitHub
Actions. No paid IFTTT plan, no paid Zapier plan, no server to run.

## Setup

1. **Get a free NYT API key**
   - Go to https://developer.nytimes.com/ and create an account.
   - Create a new "App" and enable the **Most Popular API**.
   - Copy the generated API key.

2. **Create a GitHub repo**
   - Create a new repository (private is fine) and push these files to it.

3. **Add secrets to the repo**
   - In the repo, go to Settings → Secrets and variables → Actions → New repository secret.
   - Add three secrets:
     - `NYT_API_KEY` — the key from step 1
     - `INSTAPAPER_USERNAME` — your Instapaper login email
     - `INSTAPAPER_PASSWORD` — your Instapaper login password

4. **Enable the workflow**
   - The workflow file at `.github/workflows/nyt-instapaper.yml` is already
     set to run every hour. GitHub Actions will pick it up automatically
     once the files are pushed.
   - You can also trigger it manually: go to the Actions tab → "NYT
     trending to Instapaper" → Run workflow.

## How it works

- The script calls NYT's Most Popular API for the most-viewed articles
  in the last day (closest free equivalent to "trending").
- It checks each article's URL against `seen.json` so nothing gets saved
  twice.
- New articles get POSTed to Instapaper's simple `/api/add` endpoint,
  which only needs your username and password (no separate app
  registration needed on the Instapaper side).
- After each run, the workflow commits the updated `seen.json` back to
  the repo so state carries over to the next run.

## Adjusting it

- Change `NYT_METRIC` in `nyt_to_instapaper.py` to `"emailed"` or
  `"shared"` if you'd rather track most-emailed or most-shared articles
  instead of most-viewed.
- Change `NYT_PERIOD_DAYS` to `7` or `30` for a longer trending window.
- Change the cron schedule in the workflow file to run more or less
  often (GitHub Actions cron jobs can occasionally run a few minutes
  late during high load, but this doesn't matter for this use case).

## Costs

- NYT Developer API: free tier, generous rate limits for this kind of
  low-volume polling.
- Instapaper: free account works fine with the simple add endpoint.
- GitHub Actions: free minutes cover an hourly job like this comfortably
  on both public and private repos.
