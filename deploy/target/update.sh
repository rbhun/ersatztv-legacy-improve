#!/usr/bin/env bash
# Pull the public deploy repo, refresh the fork image, apply the local overlay,
# render compose, and restart ErsatzTV.
#
# usage:
#   update.sh              # pull + build/pull image + overlay + restart
#   update.sh --overlay    # only re-apply local/repo schedules (no image rebuild)
#   update.sh --image      # only rebuild/pull image + restart
#   update.sh --no-pull    # skip git pull of the deploy repo
set -euo pipefail

die() { echo "error: $*" >&2; exit 1; }

MODE=all
DO_PULL=1
for arg in "$@"; do
    case "$arg" in
        --overlay) MODE=overlay ;;
        --image)   MODE=image ;;
        --no-pull) DO_PULL=0 ;;
        -h|--help)
            sed -n '2,12p' "$0"
            exit 0
            ;;
        *) die "unknown argument: $arg" ;;
    esac
done

# Bootstrap defaults before local/env exists.
ETV_DIR="${ETV_DIR:-/opt/ersatztv}"
DEPLOY_DIR="${DEPLOY_DIR:-/opt/ersatztv-deploy}"
LOCAL_ENV="${ETV_DIR}/local/env"

[ -f "$LOCAL_ENV" ] || die "missing ${LOCAL_ENV} — copy deploy/local.example/ to ${ETV_DIR}/local/ and edit env"
# shellcheck disable=SC1090
set -a
# shellcheck disable=SC1091
. "$LOCAL_ENV"
set +a

: "${DEPLOY_DIR:?}"
: "${ETV_DIR:?}"
: "${ETV_IMAGE:?}"
: "${IMAGE_MODE:=build}"
: "${TZ:?}"
: "${ETV_PORT:?}"
: "${MEDIA_PATH:?}"
: "${RENDER_NODE:=/dev/dri/renderD128}"

HERE=$(cd "$(dirname "$0")" && pwd)
export DEPLOY_DIR ETV_DIR

if [ "$DO_PULL" -eq 1 ]; then
    [ -d "$DEPLOY_DIR/.git" ] || die "${DEPLOY_DIR} is not a git checkout"
    echo "==> pulling ${DEPLOY_DIR}"
    git -C "$DEPLOY_DIR" pull --ff-only
fi

render_compose() {
    echo "==> rendering docker-compose.yml"
    template="${DEPLOY_DIR}/deploy/compose/docker-compose.yml.template"
    [ -f "$template" ] || die "missing compose template at $template"

    if [ -e "$RENDER_NODE" ]; then
        RENDER_GID=$(stat -c '%g' "$RENDER_NODE")
    else
        echo "warning: ${RENDER_NODE} missing — compose will still reference /dev/dri" >&2
        RENDER_GID=0
    fi

    MEM_KB=$(awk '/^MemTotal:/{print $2}' /proc/meminfo 2>/dev/null || echo 8388608)
    TMPFS_MB=$(( MEM_KB / 1024 / 4 ))
    [ "$TMPFS_MB" -gt 4096 ] && TMPFS_MB=4096
    [ "$TMPFS_MB" -lt 1024 ] && TMPFS_MB=1024

    export ETV_IMAGE TZ ETV_PORT ETV_DIR MEDIA_PATH RENDER_GID TMPFS_MB
    # envsubst if available; otherwise a tiny python fallback.
    if command -v envsubst >/dev/null 2>&1; then
        envsubst '${ETV_IMAGE} ${TZ} ${ETV_PORT} ${ETV_DIR} ${MEDIA_PATH} ${RENDER_GID} ${TMPFS_MB}' \
            < "$template" > "${ETV_DIR}/docker-compose.yml"
    else
        python3 - "$template" "${ETV_DIR}/docker-compose.yml" <<'PY'
import os, sys
src, dst = sys.argv[1], sys.argv[2]
keys = ["ETV_IMAGE", "TZ", "ETV_PORT", "ETV_DIR", "MEDIA_PATH", "RENDER_GID", "TMPFS_MB"]
text = open(src).read()
for k in keys:
    text = text.replace("${%s}" % k, os.environ[k])
open(dst, "w").write(text)
PY
    fi
}

do_image() {
    case "$IMAGE_MODE" in
        build)
            bash "${HERE}/build-image.sh"
            ;;
        pull)
            echo "==> pulling ${ETV_IMAGE}"
            docker pull "$ETV_IMAGE"
            ;;
        *)
            die "IMAGE_MODE must be build or pull (got ${IMAGE_MODE})"
            ;;
    esac
}

do_overlay() {
    bash "${HERE}/apply-overlay.sh"
}

do_restart() {
    render_compose
    echo "==> restarting ersatztv"
    if systemctl is-enabled ersatztv >/dev/null 2>&1; then
        systemctl restart ersatztv
    else
        docker compose -f "${ETV_DIR}/docker-compose.yml" up -d
    fi
    if [ -f "${ETV_DIR}/.build-cache/last-version" ]; then
        echo "running image version: $(cat "${ETV_DIR}/.build-cache/last-version")"
    fi
}

case "$MODE" in
    all)
        do_image
        do_overlay
        do_restart
        ;;
    overlay)
        do_overlay
        echo "(compose/image unchanged)"
        ;;
    image)
        do_image
        do_restart
        ;;
esac

echo
echo "done."
