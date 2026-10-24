# SheetCheck

Checks ACS Civils daily allocation sheet PDFs (one page = one gang's day) for errors before sign-off.
Live at https://sheetcheck-gamma.vercel.app (Vercel project `sheetcheck`, team `pearse13s-projects`).
Every push to `main` on GitHub (Pearse13/allocation-checker) auto-deploys to production.

## Layout

- `app.py`: FastAPI app, deployed as a single Vercel Python function. Endpoints:
  - `POST /api/parse`: one PDF in, parsed pages out (dates as ISO strings).
  - `POST /api/check`: all parsed pages in. Groups them by gang (from the page header, not the uploader slot), runs per-day, cross-gang and offhire checks, and returns summary, gangs, cross_gang and unseen_plant.
  - `GET /api/config`: the current known lists.
  - `POST /api/config/update`: `add_operative`, `edit_operative` (rename or change trade), `remove_operative`, `add_prelim` / `edit_prelim` (name, trade, optional `from`/`until` ISO dates), `remove_prelim`, `add_plant` or `offhire`. No passcode: anyone with the link can edit the lists.
  - It also mounts `public/` as static files, but only for local dev. On Vercel the CDN serves `public/`.
- `parser.py`: pdfplumber table extraction for the fixed 19-column Excel template, plus `infer_missing_fields` for gang and date.
- `checks.py`: every check. Each one takes `config` as an argument (loaded once per request). Issues are dicts like `{severity, check, message, day, gang, action}`. `action` tells the UI which button to show (`add_operative`, `add_plant` with an optional `suggestion`, or `offhire`).
- `storage.py`: where the known lists live. On Vercel that's Upstash Redis, key `sheetcheck:config`, via the env vars `KV_REST_API_URL` and `KV_REST_API_TOKEN`. Locally it's `.local-config.json` (gitignored).
- `config.json`: **seed only**. It's copied into Redis on the first read when the key is empty. Editing it does NOT change the live lists; those are changed through the app.
- `public/index.html`: the whole front end. Vanilla JS, no build step, dark theme. Sheet text is always inserted via `textContent` (the `el()` helper), never `innerHTML`.

## Behaviour worth knowing

- Expected hours per row are 10.5. Start and finish times must be 0800 and 1800. Prelim operatives must have Job 1 = 0.5 and Job 2 = 10.
- Prelim operatives (site management, e.g. the works manager and foreman) can have optional `from`/`until` dates. They're only required on sheets dated in that range, and one found on a sheet after their `until` date gets a warning. This handles a replacement, e.g. Peter Giblin → Wayne Marriott, without flagging older or newer sheets.
- The cross-gang duplicate check only covers `vehicle_plant`; prelim operatives and plant are exempt.
- **Offhire prompts** ("Has this been offhired? Is this gone?") come up in two cases:
  - Known plant on a gang's sheet one day and gone the next (unless it moved to another gang that day).
  - Known plant not on any sheet in the upload.

  Required plant (hand tools, saws, chains) is excluded from both. Answering yes removes the item from `known_plant`, `vehicle_plant` and `prelim_plant`. A close misspelling on the next day's sheet counts as the item still being present, so a typo isn't treated as an offhire.
- **"Did you mean X?"** uses `difflib` with a cutoff of 0.8. Saying yes is handled client-side only and applies to **that one sheet page**, not every page with the same misspelling. It changes the parsed data in the browser and re-runs `/api/check` without re-uploading. The PDFs and the known lists are never changed. Corrections last for the browser session and are listed in "Spelling fixes to make" with an Undo button.
- After any list edit or correction, the UI re-runs `/api/check` on the pages it already parsed (`lastDays`).
- Request bodies over 4.5 MB are rejected by Vercel, which is why each PDF goes to `/api/parse` separately.

## Local dev

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt uvicorn
```

```bash
.venv/bin/uvicorn app:app --port 8000
```

Sample sheets are in `~/Downloads/21.09 - 23.09 *Gang*.pdf`. Running all three should give 6 errors, 4 warnings and 3 cross-gang duplicates with the seed config. Don't commit PDFs (they're gitignored).

## Deploying

Push to `main`. Env vars are managed in Vercel (`vercel env ls`). After changing an env var, redeploy with `vercel deploy --prod`.
