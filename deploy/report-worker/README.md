# Wrong-answer reports

What a report contains, where it goes and what it is used for is in the main
README under "Reporting wrong answers"; this file is how to run the mailbox.

A Cloudflare Worker with a D1 table. Free tier, no server to keep alive.
The page's **Report a wrong answer** form posts here; nothing is sent unless
someone fills that form in and presses Send.

Once, from this directory:

```bash
npm install -g wrangler
wrangler login
wrangler d1 create kobold-reports          # paste the printed database_id into wrangler.toml
wrangler d1 execute kobold-reports --remote --file schema.sql
wrangler secret put ADMIN_KEY            # anything long; needed to read reports back
wrangler secret put SALT                 # anything; salts the IP hash used for rate limiting
wrangler deploy                          # prints https://kobold-reports.<you>.workers.dev
```

This project's own deployment is `https://kobold-reports.deastiny.workers.dev` and is
the app's default. To use your own, run the app with that URL:

```bash
kobold serve --report-url https://kobold-reports.<you>.workers.dev
# or KOBOLD_REPORT_URL=… kobold serve
```

Reading them:

```bash
curl "https://kobold-reports.<you>.workers.dev/reports.md?key=$ADMIN_KEY"
```

What a report carries: the question, the answer as shown, the correction typed
in, an optional source URL, the names and URLs of the entries the answer was
built from, the model and index tag, and the app version. No key, no settings,
no history. A hash of the sender's IP is kept for the 20-a-day limit and
nothing else.

Without a report URL the form still works: it opens a pre-filled GitHub issue
for the repository, or copies the report as Markdown.
