# Patches

Improvements live here as `git format-patch` series against the upstream tags in
[`versions.env`](../versions.env). The deploy build clones upstream, applies these, then
compiles — so this public repo does not need to vendor the full ErsatzTV / Next trees.

| Directory | Upstream | Current series |
|---|---|---|
| `legacy/` | [ErsatzTV/ErsatzTV](https://github.com/ErsatzTV/ErsatzTV) @ `LEGACY_TAG` | multi-audio, credit skip (+ Settings→Playout UI), Health Check update panel, performance page |
| `next/` | [ErsatzTV/next](https://github.com/ErsatzTV/next) @ `NEXT_TAG` | multi-audio tracks |

When offering something upstream, open a PR against the real project from a throwaway branch;
keep the patch here until it lands (then drop it on the next rebase).
