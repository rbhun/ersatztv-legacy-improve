# Deploy from GitHub

Public repo: [`rbhun/ersatztv-legacy-improve`](https://github.com/rbhun/ersatztv-legacy-improve).

The host that runs ErsatzTV **pulls** this repo and the public fork sources, then applies a
**local overlay** that never goes online.

## Layout on the target

| Path | Role |
|---|---|
| `/opt/ersatztv-deploy` | `git clone` of this public repo |
| `/opt/ersatztv/local/` | Personal overlay (`env`, optional schedule overrides) — **not** in git |
| `/opt/ersatztv/config/` | ErsatzTV database + live schedules (bind-mounted into the container) |
| `/opt/ersatztv/docker-compose.yml` | Rendered from `deploy/compose/*.template` + `local/env` |
| `/opt/ersatztv/build/` | Working checkouts of the public Legacy / Next forks |

## First time

```bash
# on the ErsatzTV LXC, as root
curl -fsSL https://raw.githubusercontent.com/rbhun/ersatztv-legacy-improve/main/deploy/target/bootstrap.sh \
  | bash
# edit /opt/ersatztv/local/env, then:
ersatztv-update
```

`bootstrap.sh` will not wipe an existing `/opt/ersatztv/config` database.

## Everyday update

```bash
ersatztv-update              # git pull + build/pull image + overlay + restart
ersatztv-update --overlay    # schedules/selectors only
ersatztv-update --image      # image only
ersatztv-update --no-pull    # use the deploy checkout already on disk
```

## Local overlay rules

Defaults come from `ersatztv/*.yml` in this public repo.

If `/opt/ersatztv/local/schedules/main.yml` (same for the other five, and for
`stream-selectors/` / `graphics/`) exists, **that file wins** on every
`ersatztv-update`. Put experiments and site-specific tweaks there so a `git pull`
cannot overwrite them.

`local/env` holds host-specific values (timezone, render node, image name, fork URLs).
No tokens or LAN addresses belong in the public git history.

## Public fork sources

| Repo | Branch | Purpose |
|---|---|---|
| [`rbhun/ersatztv`](https://github.com/rbhun/ersatztv) | `multi-audio` | Legacy + Next-engine UI/fork commits |
| [`rbhun/ersatztv-next`](https://github.com/rbhun/ersatztv-next) | `multi-audio` | Next engine fork (multi-audio tracks) |

`IMAGE_MODE=build` (default) clones those branches on the target and builds
`ersatztv:multi-audio` plus a versioned tag `ersatztv:<legacy>-fork.<sha>` for rollback.

## Manual schedule push from a laptop

`scripts/deploy_ersatztv.sh user@host` still works for copying YAML over SSH with md5
checks. Prefer `ersatztv-update --overlay` on the host once the git deploy is wired, so
the same overlay rules apply.
