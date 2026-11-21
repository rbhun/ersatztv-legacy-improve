# AGENTS.md — TV station

This folder is the user's six-channel ErsatzTV station that feeds Plex Live TV. It is its own git
repo, nested inside a clone of the upstream ErsatzTV source. The clone's git ignores it (through
`.git/info/exclude`), so nothing here can be pushed to github.com/ErsatzTV. Do not commit station
files to the clone, and do not touch the clone's own files or branches unless asked.

The history before 2026-11-20 is on the HA repo's `ersatztv-archive` branch.

This repo is public on GitHub (`rbhun/ersatztv-legacy-improve`). Never commit IP addresses,
tokens, API keys or library file listings; use `plex.internal` or `<host>` placeholders.

## Layout

- `ersatztv/*.yml`: the six sequential schedules, two stream selectors and graphics. They are
  deployed to `/opt/ersatztv/config/sequential-schedules/` in the ErsatzTV container (LXC 230).
- `ersatztv/audit/`: library inventory snapshots that the checkers read. Local only (gitignored);
  regenerate with `scripts/plex_library_audit.py`.
- `scripts/`: run them from this folder, because they use paths relative to it.
  - `check_watershed.py` must exit 0 after any schedule change.
  - `count_ersatztv_queries.py --url http://<etv-host>:8409` counts the live index (read-only).
- `docs/changes-log.md`: log every change here, newest at the end.

## Rules

- The user runs deploys, installs, Plex setting changes and HTTP writes. Read-only GETs to Plex
  and ErsatzTV are fine. The guard hook in `../.cursor/hooks/` enforces the infrastructure
  limits.
- In the ErsatzTV UI, only change what the user has authorised for that session.
- Never print the Plex token (`~/.plex_token`). Redact tokens and API keys from any log
  output you quote.
- Record the md5 of every schedule file the user is asked to deploy, in the log entry.
