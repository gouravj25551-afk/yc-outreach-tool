# YC Outreach

Pick any Y Combinator batch, get every company's founders and their likely email addresses, and write a personalised
cold email to each one from a single template. Free by default (no API keys, no sign-up); optional verified emails
with your own Apify token.

```
python3 serve.py        # open http://localhost:8765
```

Python 3.9+, standard library only. Nothing to install.

## Setup

Copy `.env.example` for the full list of variables. Locally, the simplest way to set them is as plain files next to
`serve.py` (all gitignored) rather than exporting env vars:

- `.site_password` — one line, the password that gates the site. **Required.**
- `.gmail_app_password` — one line, a Gmail app password (Google Account -> Security -> 2-Step Verification ->
  App passwords; not your normal password). Sends drafts from `GMAIL_USER`. Optional — the UI falls back to opening
  a Gmail compose window instead.
- `.gmail_accounts.json` — instead of the above, a JSON array to spread sends across several accounts:
  `[{"email":"a@gmail.com","password":"app-password","cap":20}, ...]`.

For the three-account rotation, copy `gmail_accounts.example.json` to `.gmail_accounts.json`, then put each
account's Gmail app password in its `password` field. The tool creates the first 20 drafts in
`gouravjain3107@gmail.com`, the next 20 in `gj9853@gmail.com`, and the last 20 in
`gouravjain6969@gmail.com`. The limit resets at local midnight. Creating a draft consumes one slot even if you
later delete it or decide not to send it.

Then set `GMAIL_USER` (and `APIFY_TOKEN` / `BLOB_READ_WRITE_TOKEN` if you want those) as real environment variables,
and run:

```
GMAIL_USER=you@gmail.com python3 serve.py
```

On Vercel, set the same names (`SITE_PASSWORD`, `GMAIL_USER`, `GMAIL_APP_PASSWORD` or `GMAIL_ACCOUNTS`, `APIFY_TOKEN`,
`BLOB_READ_WRITE_TOKEN`) as project environment variables instead of local files.

## What it does

1. **Pick a batch** (Summer 2005 through the latest) from YC's public directory.
2. **Founders load 20 companies at a time** (about 5–10 s per 20); click **Load more** for the next 20. For each
   company the server reads its ycombinator.com page for the founders' names, titles, LinkedIn and X, and for how
   many roles that company has open on YC (title and link for each). Loaded companies are kept in your browser, so
   reopening a batch is instant. Check **hiring** to hide companies with no open roles.
3. **Emails are filled in** for each founder, best source first:

   | Label | Source | Reliability |
   |---|---|---|
   | `verified` | Apify lookup with your token (optional) | Checked by Apify |
   | `unverified` | Apify lookup that couldn't confirm the mailbox | Usually right |
   | `on site` | Email published on the company's homepage or `/contact` page | Real address, may be generic |
   | `guess` | `first@domain`, then `first.last@`, `flast@`, `firstlast@` | First guess right ~80% of the time |

   The reliability figure comes from a check against 151 Apify-verified founder emails: the first guess matched 80%, and
   the right address was somewhere in the guess list 93% of the time.
4. **Write once, send many.** Fill in your name and links, edit the subject and body, and every draft updates live.
   Copy the text or open it in your mail app. Mark companies as sent to hide them.
5. **Follow up.** Once a company is marked sent, a short follow-up template ("Any update worth a two-line reply?")
   appears on its page. Follow-ups are capped at 10 per Gmail account per day (so 10 × your number of accounts
   total) - once every account hits that cap, sending is blocked for the day with a warning. The tracker page is
   split into an Outreach half and a Follow-ups half, each with its own daily/weekly/monthly counts.

Your details, template, "sent" marks and loaded batches are stored in your browser (`localStorage`). There's no
database and no account.

## Deploy

Import the repo on [Vercel](https://vercel.com/new). No build step. Set the environment variables from
[Setup](#setup) in the project settings. `index.html` is served as a static page, and `api/yc.py`, `api/draft.py`
and `api/track.py` each run as a Python serverless function (`vercel.json` gives them 60 s).

## Project layout

| File | Role |
|---|---|
| `index.html` | The whole UI: one HTML file with inline CSS and JS, no framework, no build. |
| `api/yc.py` | Serverless function (Vercel Python runtime, `handler` class). YC search + founder pages. |
| `api/draft.py` | Serverless function: saves an email as a Gmail draft via IMAP. |
| `api/track.py` | Serverless function: the "sent" tracker, persisted in Vercel Blob. |
| `serve.py` | Local dev server: serves `index.html` and routes `/api/*` to the same handlers. |
| `vercel.json` | Function timeout. |
| `yc_scraper.py` | CLI: scrape whole batches to JSON/CSV. |
| `apify_enrich.py` | CLI: add Apify-found emails to the scraper's output. |

## HTTP API

All endpoints are `GET` and return JSON. Errors return `{"error": "..."}` with status 400 (bad input) or 502 (YC
unreachable).

### `/api/yc?action=batches`

```json
[{"batch": "Fall 2026", "count": 110}, {"batch": "Summer 2026", "count": 231}]
```

Newest first. Includes `"Unspecified"`, which the UI hides.

### `/api/yc?action=companies&batch=Winter%202024`

```json
[{"name": "Indemni", "slug": "indemni", "batch": "Winter 2024", "website": "http://www.indemni.com",
  "one_liner": "Cargo Theft and Fraud Prevention Platform", "industry": "B2B -> Supply Chain and Logistics",
  "team_size": 7, "launched_at": 1708029636}]
```

`batch` must look like `Winter 2024` (season + year).

### `/api/yc?action=founders&slugs=indemni,parcelbio`

At most 10 slugs per call (`^[a-z0-9-]+$`). The UI loads 20 companies per click as two parallel calls. About
5–9 s per call; each company's website check is cut off after 4 s (`SITE_DEADLINE`) so one slow site can't stall
the batch.

```json
[{"slug": "indemni", "website": "http://www.indemni.com", "domain": "indemni.com",
  "linkedin": "https://www.linkedin.com/company/...", "twitter": "", "site_emails": [],
  "job_count": 1, "jobs": [{"title": "Founding Engineer", "url": "https://www.ycombinator.com/companies/indemni/jobs/..."}],
  "founders": [{"name": "Omar Draz", "title": "Founder", "linkedin": "https://linkedin.com/in/odraz",
                "twitter": "https://twitter.com/oamdraz", "emails_found": [],
                "email_guesses": ["omar@indemni.com", "omar.draz@indemni.com", "odraz@indemni.com", "omardraz@indemni.com"]}]}]
```

A company whose YC page fails to load comes back as `{"slug": "...", "error": "..."}`. Guesses are empty when the
domain doesn't resolve.

## Where the data comes from

- **Batches and companies:** YC's public company search (Algolia). The read-only search key is read from
  `ycombinator.com/companies` at runtime, so no key is stored here.
- **Founders and open roles:** the `data-page` JSON embedded in each `ycombinator.com/companies/<slug>` page
  (`props.company` and `props.jobPostings`). Incomplete postings are skipped. Browsers can't fetch these
  cross-origin, which is why this part runs on a server.
- **Verified emails (optional):** the Apify actor
  [`snipercoder/email-finder-by-name-and-domain`](https://apify.com/snipercoder/email-finder-by-name-and-domain),
  called **from the browser** with the visitor's own token, so the token never reaches the server. Results are
  matched on the `Name` and `Domain` fields of each dataset item. Each run covers up to 50 founders and is capped
  with `maxTotalChargeUsd`.

## Command line

For bulk exports. Output files are gitignored.

```
python3 yc_scraper.py --batches "Winter 2024" "Summer 2024" --out yc_founders   # -> yc_founders.json + .csv
python3 apify_enrich.py --input yc_founders.json --out yc_founders_enriched      # needs APIFY_TOKEN
```

`yc_scraper.py` flags: `--batches` (default `"Summer 2026" "Fall 2026"`), `--out`, `--workers` (default 12),
`--limit` (first N companies, for testing). It checks six contact pages per site and retries, so it's slower but
more thorough than the web API.

`apify_enrich.py` reads `APIFY_TOKEN` from the environment or a `.env` file (gitignored). Flags: `--input`, `--out`,
`--limit`, `--chunk` (founders per run, default 50), `--max-charge` (USD cap per run, default 1).

## Notes for AI agents and contributors

- Standard library only, on purpose. Don't add dependencies or a build step.
- `api/yc.py` and `yc_scraper.py` share logic but are separate on purpose: the function has to finish inside a
  serverless timeout, so it makes one attempt per fetch, checks 2 pages, and gives up on a website after 4 s;
  the CLI retries and checks 6.
- The function only accepts a batch name or slugs. Websites always come from YC's data, never from the request, so
  it can't be used to fetch arbitrary URLs. Keep it that way.
- Everything from YC is untrusted text. `index.html` escapes it (`esc()`) and only links `http(s)` URLs (`url()`).
- To test locally: `python3 serve.py`, then
  `curl 'localhost:8765/api/yc?action=founders&slugs=reddit'`.

## Be decent

Write to people one at a time, keep it short, and take "no" for an answer.

## License

MIT
