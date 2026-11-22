#!/usr/bin/env bash
# First-time wiring on the ErsatzTV host (LXC).
#
# usage:
#   curl -fsSL https://raw.githubusercontent.com/rbhun/ersatztv-legacy-improve/main/deploy/target/bootstrap.sh | sudo bash
#   # or, from a checkout:
#   sudo bash deploy/target/bootstrap.sh [git-url]
#
# Creates:
#   /opt/ersatztv-deploy     public git checkout (schedules + patches + deploy)
#   /opt/ersatztv/local/     personal overlay (env + optional schedule overrides)
#   /opt/ersatztv/config/    ErsatzTV bind-mount (left alone if it already exists)
set -euo pipefail

REPO_URL="${1:-https://github.com/rbhun/ersatztv-legacy-improve.git}"
DEPLOY_DIR="${DEPLOY_DIR:-/opt/ersatztv-deploy}"
ETV_DIR="${ETV_DIR:-/opt/ersatztv}"

die() { echo "error: $*" >&2; exit 1; }

if [ "$(id -u)" -ne 0 ]; then
    die "run as root (sudo)"
fi

command -v git >/dev/null || die "install git first"
command -v docker >/dev/null || die "install docker first (see scripts/install_ersatztv_plex_vm.sh)"

echo "==> checkout ${REPO_URL} -> ${DEPLOY_DIR}"
if [ -d "$DEPLOY_DIR/.git" ]; then
    git -C "$DEPLOY_DIR" remote set-url origin "$REPO_URL"
    git -C "$DEPLOY_DIR" pull --ff-only
else
    mkdir -p "$(dirname "$DEPLOY_DIR")"
    git clone "$REPO_URL" "$DEPLOY_DIR"
fi

echo "==> preparing ${ETV_DIR}/local overlay"
mkdir -p "${ETV_DIR}/config" "${ETV_DIR}/local"
if [ ! -f "${ETV_DIR}/local/env" ]; then
    cp -R "${DEPLOY_DIR}/deploy/local.example/." "${ETV_DIR}/local/"
    TZ_VALUE=$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || echo Europe/Budapest)
    RENDER_NODE=""
    if [ -e /dev/dri/renderD128 ]; then
        RENDER_NODE=/dev/dri/renderD128
    else
        for n in /dev/dri/renderD*; do
            [ -e "$n" ] || continue
            RENDER_NODE=$n
            break
        done
    fi
    [ -n "$RENDER_NODE" ] || RENDER_NODE=/dev/dri/renderD129
    sed -i "s|^TZ=.*|TZ=${TZ_VALUE}|" "${ETV_DIR}/local/env" 2>/dev/null \
        || sed -i '' "s|^TZ=.*|TZ=${TZ_VALUE}|" "${ETV_DIR}/local/env"
    sed -i "s|^RENDER_NODE=.*|RENDER_NODE=${RENDER_NODE}|" "${ETV_DIR}/local/env" 2>/dev/null \
        || sed -i '' "s|^RENDER_NODE=.*|RENDER_NODE=${RENDER_NODE}|" "${ETV_DIR}/local/env"
    echo "    wrote ${ETV_DIR}/local/env (TZ=${TZ_VALUE}, RENDER_NODE=${RENDER_NODE})"
else
    echo "    keeping existing ${ETV_DIR}/local/env"
fi

chmod +x "${DEPLOY_DIR}/deploy/target/"*.sh

cat > /usr/local/bin/ersatztv-update <<EOF
#!/bin/sh
exec ${DEPLOY_DIR}/deploy/target/update.sh "\$@"
EOF
chmod 755 /usr/local/bin/ersatztv-update

cat <<EOF

Bootstrap complete.

Next:
  1. Review ${ETV_DIR}/local/env
  2. Run:  ersatztv-update
     (pulls this repo, clones upstream + applies patches/, builds image, applies schedules)

Local schedule overrides go in ${ETV_DIR}/local/schedules/ (same filenames as the public
ersatztv/*.yml files). Anything there wins over the public defaults on every update.
EOF
