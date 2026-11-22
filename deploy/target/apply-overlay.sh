#!/usr/bin/env bash
# Merge public repo schedules/selectors/graphics with /opt/ersatztv/local overrides
# and install them into the live ErsatzTV config bind-mount.
#
# usage: apply-overlay.sh
#   Reads DEPLOY_DIR and ETV_DIR from the environment (set by update.sh), or defaults.
set -euo pipefail

DEPLOY_DIR="${DEPLOY_DIR:-/opt/ersatztv-deploy}"
ETV_DIR="${ETV_DIR:-/opt/ersatztv}"
LOCAL_DIR="${ETV_DIR}/local"
CONFIG="${ETV_DIR}/config"

SCHED_DST="${CONFIG}/sequential-schedules"
SEL_DST="${CONFIG}/scripts/channel-stream-selectors"
GFX_DST="${CONFIG}/graphics"

SCHEDULES=(main.yml main-hu.yml kids.yml kids-hu.yml movies.yml movies-hu.yml)
SELECTORS=(stream-selector-en.yml stream-selector-hu.yml)

die() { echo "error: $*" >&2; exit 1; }

local_md5() {
    if command -v md5sum >/dev/null 2>&1; then md5sum "$1" | awk '{print $1}'
    else md5 -q "$1"; fi
}

# Resolve one file: local overlay wins, else public repo.
resolve() {
    # resolve <filename> <local-subdir>
    name=$1
    local_sub=$2
    local_file="${LOCAL_DIR}/${local_sub}/${name}"
    repo_file="${DEPLOY_DIR}/ersatztv/${name}"
    if [ -f "$local_file" ]; then
        printf '%s|local' "$local_file"
    elif [ -f "$repo_file" ]; then
        printf '%s|repo' "$repo_file"
    else
        die "missing ${name} (not in local/${local_sub}/ and not in repo ersatztv/)"
    fi
}

install_file() {
    src=$1 dst=$2
    if install -m 644 "$src" "$dst" 2>/dev/null; then
        return
    fi
    cp "$src" "$dst"
    chmod 644 "$dst"
}

[ -d "$DEPLOY_DIR/ersatztv" ] || die "DEPLOY_DIR=${DEPLOY_DIR} has no ersatztv/; clone the public repo there"
mkdir -p "$SCHED_DST" "$SEL_DST" "$GFX_DST" \
    "$LOCAL_DIR/schedules" "$LOCAL_DIR/stream-selectors" "$LOCAL_DIR/graphics"

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

echo "==> resolving schedules (local overlay wins)"
for f in "${SCHEDULES[@]}"; do
    IFS='|' read -r src origin <<<"$(resolve "$f" schedules)"
    cp "$src" "$STAGE/$f"
    printf '    %-5s %s\n' "$origin" "$f"
done

echo "==> resolving stream selectors"
for f in "${SELECTORS[@]}"; do
    IFS='|' read -r src origin <<<"$(resolve "$f" stream-selectors)"
    cp "$src" "$STAGE/$f"
    printf '    %-5s %s\n' "$origin" "$f"
done

echo "==> installing into ${CONFIG}"
for f in "${SCHEDULES[@]}"; do
    install_file "$STAGE/$f" "$SCHED_DST/$f"
done
for f in "${SELECTORS[@]}"; do
    install_file "$STAGE/$f" "$SEL_DST/$f"
done

# Graphics: repo defaults, then local overlays on top.
if [ -d "${DEPLOY_DIR}/ersatztv/graphics" ]; then
    for src in "${DEPLOY_DIR}/ersatztv/graphics"/*; do
        [ -f "$src" ] || continue
        install_file "$src" "$GFX_DST/$(basename "$src")"
    done
fi
if [ -d "${LOCAL_DIR}/graphics" ]; then
    for src in "${LOCAL_DIR}/graphics"/*; do
        [ -f "$src" ] || continue
        echo "    local  graphics/$(basename "$src")"
        install_file "$src" "$GFX_DST/$(basename "$src")"
    done
fi

echo "==> verifying"
fail=0
for f in "${SCHEDULES[@]}"; do
    want=$(local_md5 "$STAGE/$f")
    got=$(local_md5 "$SCHED_DST/$f")
    if [ "$want" = "$got" ]; then
        printf '    ok    %-26s %s\n' "$f" "$got"
    else
        printf '    STALE %-26s\n' "$f"
        fail=1
    fi
done
for f in "${SELECTORS[@]}"; do
    want=$(local_md5 "$STAGE/$f")
    got=$(local_md5 "$SEL_DST/$f")
    if [ "$want" = "$got" ]; then
        printf '    ok    %-26s %s\n' "$f" "$got"
    else
        printf '    STALE %-26s\n' "$f"
        fail=1
    fi
done
[ "$fail" -eq 0 ] || die "overlay verification failed — live config was not updated cleanly"

cat <<'EOF'

Overlay applied. If schedule content changed, finish manually:

  1. ErsatzTV  Scheduling -> Playouts -> Reset All Playouts
  2. Plex      Live TV & DVR -> Refresh Guide
EOF
