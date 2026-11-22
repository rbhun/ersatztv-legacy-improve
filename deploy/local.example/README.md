# Local overlay (target only)

Copy this whole directory to `/opt/ersatztv/local/` on the host that runs ErsatzTV.
Do **not** commit `/opt/ersatztv/local/` anywhere.

```
/opt/ersatztv/local/
  env                 # sourced by deploy/target/update.sh
  schedules/          # optional .yml overrides (same names as ersatztv/*.yml)
  stream-selectors/   # optional stream-selector-*.yml overrides
  graphics/           # optional graphics overrides
```

## Merge rules

`apply-overlay.sh` installs into the live config bind-mount:

1. Start from the public repo defaults in `ersatztv/` (schedules, selectors, graphics).
2. If a file exists under `local/schedules/`, `local/stream-selectors/`, or `local/graphics/`,
   that file **wins**.
3. Result is written under `/opt/ersatztv/config/` and verified by md5.

Personal data (hosts, tokens, library audits, one-off schedule experiments) belongs here.
Public defaults stay in git so others can reuse the deploy tooling and baseline schedules.
