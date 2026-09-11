# Macro Events Analysis

Dashboard analyzing NQ RTH behavior around CPI, PPI, FOMC, and NFP release
days (and the trading day immediately before each), synced from the
**INDICES LOG** Notion database. Same architecture as `BACKTEST-ANALYSIS`:
Python sync script → static JSON → Chart.js dashboard, no backend, served by
GitHub Pages, Chart.js vendored locally (not loaded from a CDN, since
browser shields/ad-blockers can silently block cdnjs).

## What it shows

- **Direction bias** (UPCLOSE / DOWNCLOSE / BOTHWAYS / SIDEWAYS) for each of
  the 8 categories: CPI, Pre-CPI, PPI, Pre-PPI, FOMC, Pre-FOMC, NFP, Pre-NFP.
- **AM opening range capture rate** — the % of days where the first-hour
  range (AM DR) went on to set the day's actual RTH high or low, vs. a later
  session (11AM-1PM, 1-2PM, 3:30-4PM) taking over.

## Setup

1. Add the `NOTION_TOKEN` repo secret (Settings → Secrets and variables →
   Actions) — the same "Playbook" integration token used by
   `BACKTEST-ANALYSIS`, since it needs read access to INDICES LOG, the
   DIRECTION lookup table, and the RTH PROFILES lookup table.
2. Enable GitHub Pages: Settings → Pages → Source: `main` branch, `/ (root)`.
3. Point a cron-job.org job at:
   ```
   POST https://api.github.com/repos/munga068-ctrl/MACRO-EVENTS-ANALYSIS/actions/workflows/sync.yml/dispatches
   Body: {"ref":"main"}
   ```
   (identical setup to the other dashboards' cron jobs).

## Notes

- `scripts/sync_notion.py` finds pages by matching "CPI"/"PPI"/"FOMC"/"NFP"
  substrings in the `Name` property, and detects "Pre" days via a
  case-insensitive `pre\s*<EVENT>` regex — so tagging convention matters.
  A day tagged with two events (e.g. `#106-FOMC-PPI`) is counted in both
  categories.
- `DIRECTION_NAMES` and `RTH_AM_CAPTURE` in the sync script are hardcoded
  lookup tables (mapping Notion relation page IDs to their meaning) rather
  than resolved dynamically, since both are small, fixed sets — this avoids
  an extra Notion API call per page. If new RTH profile combinations appear
  in the data that aren't in `RTH_AM_CAPTURE`, that day's AM-capture stat is
  silently skipped (not counted as either true or false) — extend the dict
  if that starts happening a lot.
- `data/macro_events.json` ships pre-seeded with the analysis already done
  as of Sept 2026 so the dashboard isn't empty before the first live sync.
