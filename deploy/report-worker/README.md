# Wrong-answer reports

A Cloudflare Worker with a D1 table. Free tier, no server to keep alive.
The page's **Report a wrong answer** form posts here; nothing is sent unless
someone fills that form in and presses Send.

Once, from this directory:

```bash
npm install -g wrangler
wrangler login
wrangler d1 create pf2e-reports          # paste the printed database_id into wrangler.toml
wrangler d1 execute pf2e-reports --remote --file schema.sql
wrangler secret put ADMIN_KEY            # anything long; needed to read reports back
wrangler secret put SALT                 # anything; salts the IP hash used for rate limiting
wrangler deploy                          # prints https://pf2e-reports.<you>.workers.dev
```

This project's own deployment is `https://pf2e-reports.deastiny.workers.dev` and is
the app's default. To use your own, run the app with that URL:

```bash
pf2e serve --report-url https://pf2e-reports.<you>.workers.dev
# or PF2E_REPORT_URL=… pf2e serve
```

Reading them:

```bash
curl "https://pf2e-reports.<you>.workers.dev/reports.md?key=$ADMIN_KEY"
```

What a report carries: the question, the answer as shown, the correction typed
in, an optional source URL, the names and URLs of the entries the answer was
built from, the model and index tag, and the app version. No key, no settings,
no history. A hash of the sender's IP is kept for the 20-a-day limit and
nothing else.

Without a report URL the form still works: it opens a pre-filled GitHub issue
for the repository, or copies the report as Markdown.
