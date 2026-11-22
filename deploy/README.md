# Deploy from GitHub (single repo)

Public repo: [`rbhun/ersatztv-legacy-improve`](https://github.com/rbhun/ersatztv-legacy-improve).

One repository holds **everything that is yours**:

| Path | What |
|---|---|
| `ersatztv/` | Public schedule / selector / graphics defaults |
| `patches/legacy/` | Improvements on top of upstream ErsatzTV (`LEGACY_TAG`) |
| `patches/next/` | Improvements on top of upstream Next (`NEXT_TAG`) |
| `deploy/` | Target pull / build / overlay scripts |
| `versions.env` | Which upstream tags the patches apply to |

The target **pulls this repo**, clones **upstream** at the pinned tags, applies the patches,
builds the image, then merges a **local overlay** that never goes online.

The separate `rbhun/ersatztv` and `rbhun/ersatztv-next` fork repos are obsolete for deploy;
keep them only if you still want GitHub history mirrors.

## Layout on the target

| Path | Role |
|---|---|
| `/opt/ersatztv-deploy` | `git clone` of this public repo |
| `/opt/ersatztv/local/` | Personal overlay (`env`, optional schedule overrides) — **not** in git |
| `/opt/ersatztv/config/` | ErsatzTV database + live schedules (bind-mounted) |
| `/opt/ersatztv/docker-compose.yml` | Rendered from `deploy/compose/*.template` + `local/env` |
| `/opt/ersatztv/build/` | Working trees: upstream + applied patches |

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
ersatztv-update              # git pull + rebuild image from patches + overlay + restart
ersatztv-update --overlay    # schedules/selectors only
ersatztv-update --image      # image only
ersatztv-update --no-pull    # use the deploy checkout already on disk
```

Or from the ErsatzTV UI: **Support → Health Checks → Updates**. The host runs
`ersatztv-update-agent` (systemd). The page polls every 10 seconds, lets you pick a
repo/branch from `UPDATE_SOURCES`, and the Update button backs up `/opt/ersatztv/local`,
runs the update, restores local overlay, and shows a live log.

## Local overlay rules

Defaults come from `ersatztv/*.yml` in this public repo.

If `/opt/ersatztv/local/schedules/main.yml` (same for the other five, and for
`stream-selectors/` / `graphics/`) exists, **that file wins** on every
`ersatztv-update`. Put experiments and site-specific tweaks there so a `git pull`
cannot overwrite them.

`local/env` holds host-specific values (timezone, render node, image name).
No tokens or LAN addresses belong in the public git history.

## Adding or rebasing an improvement

On a machine with the upstream checkouts:

```bash
# after committing on top of LEGACY_TAG / NEXT_TAG:
git -C /path/to/ErsatzTV format-patch v26.13.0..HEAD -o patches/legacy/
git -C /path/to/ersatztv-next format-patch v0.2.7..HEAD -o patches/next/
# bump versions.env if the base tags moved, then commit
```

Verify with `git am --3way` on a clean upstream tag before pushing.
