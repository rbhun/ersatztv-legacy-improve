#!/bin/sh
# install_ersatztv_plex_vm.sh – Install ErsatzTV as a Docker container alongside Plex
#
# Run INSIDE THE PLEX HOST:  sudo sh install_ersatztv_plex_vm.sh
#
# Over SSH, allocate a TTY or sudo cannot prompt for the password:
#   scp install_ersatztv_plex_vm.sh <user>@<plex-host>:/tmp/
#   ssh -t <user>@<plex-host> 'sudo sh /tmp/install_ersatztv_plex_vm.sh'
#
# The normal login there is not root, so the script re-execs itself under sudo if you
# forget. Root is genuinely required: apt, systemd units, and /opt.
#
# Options:  --force   skip the "is this really the Plex host?" safety check
#
# WHY IT LIVES WITH PLEX (and not in its own container):
#   Chosen deliberately over a dedicated LXC/VM. Two concrete wins:
#     - The Plex host is already on the "Services WAN whitelist" firewall rule, so the
#       image pull and ErsatzTV's calls to plex.tv work with no firewall change. A new
#       host would be blocked by the "Block Services WAN" rule.
#     - ErsatzTV imports libraries from Plex over the API and then has to open the very
#       same files itself. Sharing the host means /mnt/media resolves identically for
#       both, so ErsatzTV needs no Path Replacements.
#   The cost, stated plainly: this breaks the one-service-per-container invariant in
#   docs/infrastructure-spec.md §9.6. ErsatzTV shares Plex's CPU, RAM, GPU and fate.
#
# RUNNING INSIDE AN LXC (the arrangement since 2026-11):
#   Plex now lives in an LXC with an AMD iGPU, and ErsatzTV follows it there. Two
#   container features are required on the LXC before this script will work:
#     - nesting=1, or Docker cannot start inside the LXC at all
#     - /dev/dri bound into the LXC, which is already true if Plex is using the iGPU
#   Nothing else changes: the GPU block below reads the render device's GID as seen
#   inside the LXC, which is exactly what Docker's group_add needs, privileged or not.
#
# WHY DOCKER AND NOT THE NATIVE BINARY:
#   ErsatzTV is tightly coupled to a specific FFmpeg build. The native install path has a
#   known failure mode where an upgrade leaves the service dead because bundled FFmpeg was
#   not upgraded with it (community-scripts/ProxmoxVE#5443). The official image ships the
#   matching FFmpeg, so version skew is impossible.
#
# WHAT THIS TOUCHES ON THE PLEX VM:
#   - installs Docker CE + compose plugin from Docker's official apt repo (if absent)
#   - creates /opt/ersatztv/{config,docker-compose.yml}
#   - installs /usr/local/bin/ersatztv-media-check and ersatztv.service
#   - binds /mnt/media READ-ONLY; it cannot modify your library
#   Docker adds a docker0 bridge on 172.17.0.0/16 and its own FORWARD rules. That does not
#   collide with the 192.168.x plan and Plex listens on host ports, so Plex is unaffected.
#
# BACKUP INCLUSION (invariant §9.3): /opt/ersatztv rides along in the existing Proxmox
#   snapshot backup of the Plex VM. No separate backup job is needed.
#
# THE FAILURE MODE THIS SCRIPT GUARDS HARDEST:
#   /mnt/media is NFS from proxmox.internal with x-systemd.automount. Per
#   docs/Home_Network_Reference_v8.md, a dead automount presents an EMPTY DIRECTORY rather
#   than an error — that is what made Plex serve cached metadata while playback failed. If
#   Docker bind-mounts /mnt/media while the automount is untriggered, ErsatzTV silently
#   sees zero files and every channel it builds is broken. So: the mount is verified live
#   and non-empty before install, the bind uses rslave propagation so later remounts
#   propagate into the container, and ersatztv.service refuses to start on an empty mount.
#
# Idempotent: safe to re-run. Re-running upgrades nothing by itself — see UPDATING at the
# bottom of this file, and note that ErsatzTV does NOT support downgrades.

set -eu

# ── Tunables ─────────────────────────────────────────────────────────────────
ETV_DIR="/opt/ersatztv"
MEDIA_PATH="/mnt/media"
ETV_PORT="8409"
# Pinned deliberately rather than :latest, because re-running this script rewrites
# docker-compose.yml -- on :latest that silently moves the version under you, and ErsatzTV's
# schema migrations are one-way (it does not support downgrades).
#
# v26.12.0 is the floor, not a preference. Before it, the next streaming engine played a
# `pad_until` fallback item once instead of looping it, then showed the error slate for the
# rest of the gap -- up to an hour at a time on the film channels. It also removes the
# legacy engine, so there is no per-channel rollback any more.
#
# The next engine can STREAM COPY instead of re-encoding: disable `Normalize Video` /
# `Normalize Audio` in the FFmpeg Profile and h264/hevc video and aac/ac3/eac3/mp3 audio are
# passed through untouched. Items that cannot be copied (burned-in subtitles, still images,
# other codecs) still transcode with the profile's settings. Either way a channel carries a
# single audio track and no selectable subtitle track.
ETV_IMAGE="ghcr.io/ersatztv/legacy:v26.12.0"

# ── Arguments ────────────────────────────────────────────────────────────────
# --force is a flag rather than only an env var so that it survives the sudo re-exec
# below; passing env through sudo can be refused outright by sudoers.
FORCE="${FORCE:-0}"
for arg in "$@"; do
    case "$arg" in
        --force)
            FORCE=1
            ;;
        -h|--help)
            echo "usage: sudo sh $0 [--force]"
            echo "  --force   skip the check that this host is the Plex VM"
            exit 0
            ;;
        *)
            echo "ERROR: unknown argument '${arg}' (try --help)" >&2
            exit 2
            ;;
    esac
done

# ── Preflight: root ──────────────────────────────────────────────────────────
# Re-exec under sudo instead of just failing, since the everyday login here is rbhun.
if [ "$(id -u)" -ne 0 ]; then
    if ! command -v sudo >/dev/null 2>&1; then
        echo "ERROR: needs root and sudo is not installed. Log in as root and re-run." >&2
        exit 1
    fi
    if [ ! -f "$0" ]; then
        echo "ERROR: needs root, but cannot re-exec: '$0' is not a file (piped from stdin?)." >&2
        echo "       Save the script to disk and run: sudo sh install_ersatztv_plex_vm.sh" >&2
        exit 1
    fi
    # `ssh host 'sudo ...'` allocates no TTY, so sudo has nowhere to prompt and dies with a
    # confusing askpass error. Catch it here and name the actual fix.
    if ! sudo -n true 2>/dev/null && [ ! -t 0 ]; then
        echo "ERROR: sudo needs a password but there is no terminal to prompt on." >&2
        echo "       Re-run with a TTY, e.g.:" >&2
        echo "         ssh -t <user>@<plex-host> 'sudo sh $0'" >&2
        exit 1
    fi
    echo "not root — re-running under sudo (enter your password if prompted)"
    if [ "$FORCE" = "1" ]; then
        exec sudo sh "$0" --force
    fi
    exec sudo sh "$0"
fi

# ── Preflight: correct host ──────────────────────────────────────────────────

# Running this on the Proxmox host would install Docker on the hypervisor.
if [ -d /etc/pve ] || command -v qm >/dev/null 2>&1 || command -v pct >/dev/null 2>&1; then
    echo "ERROR: this is the Proxmox host. Run it on the Plex host instead." >&2
    exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
    echo "ERROR: systemd not found; this script assumes a systemd Debian/Ubuntu guest." >&2
    exit 1
fi

if [ ! -r /etc/os-release ]; then
    echo "ERROR: /etc/os-release missing; cannot identify the distribution." >&2
    exit 1
fi
# shellcheck disable=SC1091
. /etc/os-release
DISTRO_ID="${ID:-unknown}"
CODENAME="${VERSION_CODENAME:-}"

case "$DISTRO_ID" in
    debian|ubuntu) ;;
    *)
        echo "ERROR: expected debian or ubuntu, found '${DISTRO_ID}'." >&2
        echo "       Install Docker by hand, then re-run — the rest of this script is portable." >&2
        exit 1
        ;;
esac

if [ -z "$CODENAME" ]; then
    echo "ERROR: VERSION_CODENAME missing from /etc/os-release; cannot build the Docker repo line." >&2
    exit 1
fi

# Soft confirmation that this really is the Plex host. --force overrides. This still passes
# inside the LXC, because Plex listens on 32400 there just the same.
if [ "$FORCE" != "1" ]; then
    if ! systemctl list-unit-files 2>/dev/null | grep -q '^plexmediaserver' \
       && ! ss -ltn 2>/dev/null | grep -q ':32400' ; then
        echo "ERROR: no plexmediaserver unit and nothing listening on 32400 — this may not be" >&2
        echo "       the Plex host. Re-run with --force if you are sure." >&2
        exit 1
    fi
fi

echo "host looks correct: ${DISTRO_ID} ${CODENAME}, Plex present"

# ── Preflight: the media mount (see header) ──────────────────────────────────
# Read a path inside the mount first: with x-systemd.automount nothing is mounted until
# something touches it, so checking before touching would report a false failure.
ls "$MEDIA_PATH" >/dev/null 2>&1 || true

if [ ! -d "$MEDIA_PATH" ]; then
    echo "ERROR: ${MEDIA_PATH} does not exist. Is this the Plex host?" >&2
    echo "       On the LXC the media arrives as the mp0 bind mount, e.g." >&2
    echo "       mp0: /tank/media,mp=/mnt/media,ro=1 — check it with: pct config <ctid>" >&2
    exit 1
fi

AUTOMOUNT_UNIT="$(echo "${MEDIA_PATH#/}" | tr '/' '-').automount"

# Deliberately NOT compared against `findmnt -o TARGET` output: with x-systemd.automount
# there are two stacked mounts at this same path (an autofs mount with the real nfs4 mount
# on top of it), so findmnt legitimately prints the path twice and any exact-string match
# fails on a perfectly healthy mount.
# A warning rather than fatal: the question that actually decides whether ErsatzTV can
# work is whether media is readable here, and that is the emptiness check further down.
# An LXC bind mount is a mount point too, but it is not worth failing the install over
# the shape of the mount when the content test is the one with teeth.
if ! mountpoint -q "$MEDIA_PATH" 2>/dev/null; then
    echo "WARNING: ${MEDIA_PATH} is not itself a mount point." >&2
    echo "         On a VM that means the NFS mount is not active; diagnose with:" >&2
    echo "         journalctl -u ${AUTOMOUNT_UNIT}" >&2
fi

# Asks what filesystem is *serving the path right now*, which is the question that actually
# matters. autofs here means the trigger exists but NFS never mounted underneath it.
MEDIA_FSTYPE="$(stat -f -c %T "$MEDIA_PATH" 2>/dev/null || echo unknown)"
case "$MEDIA_FSTYPE" in
    nfs|nfs4|zfs)
        ;;
    autofs)
        echo "ERROR: ${MEDIA_PATH} is still autofs — the automount trigger exists but NFS did" >&2
        echo "       not mount underneath it. This is the silent-failure case." >&2
        echo "       Diagnose with:  journalctl -u ${AUTOMOUNT_UNIT}" >&2
        exit 1
        ;;
    *)
        echo "WARNING: ${MEDIA_PATH} reports fstype '${MEDIA_FSTYPE}'; expected nfs on a VM" >&2
        echo "         or zfs via the LXC bind mount. Continuing." >&2
        ;;
esac

# The silent killer: mount present but serving nothing.
if [ -z "$(ls -A "$MEDIA_PATH" 2>/dev/null)" ]; then
    echo "ERROR: ${MEDIA_PATH} is mounted but EMPTY — the documented silent NFS failure." >&2
    echo "       Fix the mount before installing, or ErsatzTV will import zero files." >&2
    exit 1
fi

echo "media mount OK: ${MEDIA_PATH} (${MEDIA_FSTYPE}), non-empty"

# ── Preflight: port, disk, network ───────────────────────────────────────────
if ss -ltn 2>/dev/null | grep -q ":${ETV_PORT}[[:space:]]"; then
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx ersatztv; then
        echo "port ${ETV_PORT} is held by the existing ersatztv container — will reconcile"
    else
        echo "ERROR: something else is already listening on port ${ETV_PORT}." >&2
        exit 1
    fi
fi

FREE_MB="$(df -Pm /var/lib 2>/dev/null | awk 'NR==2{print $4}')"
if [ -n "${FREE_MB:-}" ] && [ "$FREE_MB" -lt 3072 ]; then
    echo "ERROR: only ${FREE_MB} MB free under /var/lib; need ~3 GB for the image." >&2
    exit 1
fi

# The Plex host is on the Services WAN whitelist, so this should succeed. If it does not,
# the whitelist rule is the first thing to check — and note a NEW host (e.g. a freshly
# created LXC) will not be on it until the rule is updated.
if ! curl -fsS -m 15 -o /dev/null https://download.docker.com/ 2>/dev/null; then
    echo "ERROR: no outbound HTTPS. This host must reach the internet to pull the image." >&2
    echo "       Check the UCG 'Services WAN whitelist' rule includes this host." >&2
    exit 1
fi

echo "port, disk and outbound HTTPS OK"

# ── Docker ───────────────────────────────────────────────────────────────────
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    echo "docker and compose plugin already present"
else
    echo "installing Docker CE and the compose plugin"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl gnupg

    install -m 0755 -d /etc/apt/keyrings
    if [ ! -s /etc/apt/keyrings/docker.asc ]; then
        curl -fsSL "https://download.docker.com/linux/${DISTRO_ID}/gpg" \
            -o /etc/apt/keyrings/docker.asc
        chmod a+r /etc/apt/keyrings/docker.asc
    fi

    ARCH="$(dpkg --print-architecture)"
    cat > /etc/apt/sources.list.d/docker.list <<EOF
deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${DISTRO_ID} ${CODENAME} stable
EOF

    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
    systemctl enable --now docker
    echo "docker installed"
fi

# ── Hardware acceleration (probe only) ───────────────────────────────────────
# The RTX A2000 is passed through to the LLM VM and GPU policy ranks LLM first
# (infrastructure-spec §4.3). Since 2026-11 Plex runs in an LXC with an AMD iGPU, so
# /dev/dri SHOULD exist here and VAAPI should be available — set the FFmpeg Profile's
# Hardware Acceleration to VAAPI once this is installed. If the device is missing,
# transcoding silently falls back to CPU, which matters because the host governor is
# deliberately 'powersave' to keep fans quiet (§4.4).
#
# The GID is read as seen from inside this host, which is exactly what Docker's group_add
# needs, whether the LXC is privileged or carries an idmap for the render group.
#
# Do NOT assume renderD128. The node number depends on how many DRM devices the kernel
# enumerated, and the Plex LXC is passed exactly one node which arrives as renderD129.
# Hardcoding 128 made this probe fail on a machine that does have a usable iGPU, and the
# consequence is the quiet CPU fallback this block exists to prevent.
ETV_DEVICES=""
RENDER_NODE=""
if [ -e /dev/dri/renderD128 ]; then
    RENDER_NODE=/dev/dri/renderD128
else
    for n in /dev/dri/renderD*; do
        [ -e "$n" ] || continue
        RENDER_NODE="$n"
        break
    done
fi

if [ -n "$RENDER_NODE" ]; then
    RENDER_GID="$(stat -c '%g' "$RENDER_NODE")"
    ETV_DEVICES="yes"
    echo "found ${RENDER_NODE} (gid ${RENDER_GID}) — wiring it up for VAAPI"
    if [ "$RENDER_NODE" != /dev/dri/renderD128 ]; then
        echo "NOTE: ffmpeg defaults to renderD128, which is not the node on this host."
        echo "      Set the FFmpeg Profile's VAAPI device to ${RENDER_NODE}."
    fi
else
    echo "WARNING: no /dev/dri — ErsatzTV will transcode on CPU." >&2
    echo "         Expected on a VM, but NOT on the Plex LXC: check the iGPU is bound" >&2
    echo "         into the container before accepting this." >&2
fi

# ── tmpfs size for /transcode ────────────────────────────────────────────────
# Keeps HLS segments in RAM instead of hammering the NVMe. Sized from this VM's RAM:
# a quarter of it, clamped to 1–4 GB.
MEM_KB="$(awk '/^MemTotal:/{print $2}' /proc/meminfo)"
TMPFS_MB="$(( MEM_KB / 1024 / 4 ))"
if [ "$TMPFS_MB" -gt 4096 ]; then
    TMPFS_MB=4096
fi
if [ "$TMPFS_MB" -lt 1024 ]; then
    TMPFS_MB=1024
fi
echo "transcode tmpfs sized at ${TMPFS_MB} MB (VM has $(( MEM_KB / 1024 )) MB RAM)"

# ── Config directory and compose file ────────────────────────────────────────
mkdir -p "${ETV_DIR}/config"

# Inherited from the host rather than hardcoded. The catch is that a freshly built LXC is
# usually UTC, and this faithfully copies that — which is the worst possible silent failure
# for this deployment, because every daypart boundary in the schedules ("10:00", "22:00",
# the 06:00 watershed) is wall-clock local time. An hour of skew moves the watershed, so
# unrestricted content can air while a UTC-correct clock insists it is still before 22:00.
# Nothing downstream would look broken; the programming would just be wrong.
TZ_VALUE="$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || echo UTC)"
echo "timezone: ${TZ_VALUE}"
case "$TZ_VALUE" in UTC|Etc/UTC|Etc/UCT|UCT|Universal|Zulu|Etc/Zulu|GMT|Etc/GMT) TZ_VALUE_IS_UTC=1 ;; *) TZ_VALUE_IS_UTC= ;; esac
if [ -n "$TZ_VALUE_IS_UTC" ] || [ -z "$TZ_VALUE" ]; then
    echo "WARNING: the host timezone is UTC. If that is not actually your local time, the" >&2
    echo "         schedules' daypart and watershed boundaries will be off by the offset." >&2
    echo "         Fix the host first, then re-run this script:" >&2
    echo "           timedatectl set-timezone <Region/City>" >&2
    echo "         Or fix just the container: edit TZ in ${ETV_DIR}/docker-compose.yml and" >&2
    echo "         run 'systemctl restart ersatztv'. Verify with 'docker exec ersatztv date'." >&2
fi

# Written to a temp file and moved into place so an interrupted run cannot leave a
# half-written compose file that then fails to parse.
TMP_COMPOSE="$(mktemp)"
{
    cat <<EOF
# Managed by scripts/install_ersatztv_plex_vm.sh — re-running the script rewrites this.
services:
  ersatztv:
    image: ${ETV_IMAGE}
    container_name: ersatztv
    environment:
      - TZ=${TZ_VALUE}
    ports:
      - "${ETV_PORT}:${ETV_PORT}"
    volumes:
      - type: bind
        source: ${ETV_DIR}/config
        target: /config
      # Same path inside and out, so no ErsatzTV Path Replacements are needed for the
      # libraries it imports from Plex. read_only: Plex's library is never writable here.
      # propagation rslave: if the NFS automount expires and remounts, the container
      # follows it instead of holding a stale, empty view.
      - type: bind
        source: ${MEDIA_PATH}
        target: ${MEDIA_PATH}
        read_only: true
        bind:
          propagation: rslave
    tmpfs:
      - /transcode:size=${TMPFS_MB}m,mode=1777
    restart: unless-stopped
EOF

    if [ -n "$ETV_DEVICES" ]; then
        cat <<EOF
    devices:
      - /dev/dri:/dev/dri
    group_add:
      - "${RENDER_GID}"
EOF
    fi
} > "$TMP_COMPOSE"

install -m 0644 -o root -g root "$TMP_COMPOSE" "${ETV_DIR}/docker-compose.yml"
rm -f "$TMP_COMPOSE"
echo "wrote ${ETV_DIR}/docker-compose.yml"

# ── Media guard used by the systemd unit ─────────────────────────────────────
cat > /usr/local/bin/ersatztv-media-check <<EOF
#!/bin/sh
# Managed by scripts/install_ersatztv_plex_vm.sh.
# Refuse to start ErsatzTV against a dead NFS mount. An empty ${MEDIA_PATH} is the
# documented silent-failure signature, so treat empty as fatal rather than starting and
# serving broken channels.
set -eu
# Read inside the path first: with x-systemd.automount nothing is mounted until touched.
ls "${MEDIA_PATH}" >/dev/null 2>&1 || true

if ! mountpoint -q "${MEDIA_PATH}" 2>/dev/null; then
    echo "ersatztv: ${MEDIA_PATH} is not mounted; refusing to start." >&2
    exit 1
fi

# autofs means the trigger is there but NFS never mounted under it. Note this checks the
# serving filesystem rather than matching findmnt output, because the automount leaves two
# stacked mounts on this same path and a string match would fail on a healthy mount.
if [ "\$(stat -f -c %T "${MEDIA_PATH}" 2>/dev/null || echo unknown)" = "autofs" ]; then
    echo "ersatztv: ${MEDIA_PATH} is still autofs, NFS not mounted; refusing to start." >&2
    exit 1
fi

if [ -z "\$(ls -A "${MEDIA_PATH}" 2>/dev/null)" ]; then
    echo "ersatztv: ${MEDIA_PATH} is mounted but empty; refusing to start." >&2
    exit 1
fi
EOF
chmod 0755 /usr/local/bin/ersatztv-media-check
echo "installed /usr/local/bin/ersatztv-media-check"

# ── systemd unit ─────────────────────────────────────────────────────────────
# compose's own restart policy already handles crashes and boot. This unit exists for
# ordering: RequiresMountsFor pulls in the /mnt/media automount before the container, and
# ExecStartPre blocks startup on a dead mount.
DOCKER_BIN="$(command -v docker)"
cat > /etc/systemd/system/ersatztv.service <<EOF
[Unit]
Description=ErsatzTV (docker compose)
Documentation=https://ersatztv.org/docs/
Requires=docker.service
After=docker.service network-online.target
RequiresMountsFor=${MEDIA_PATH}

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${ETV_DIR}
ExecStartPre=/usr/local/bin/ersatztv-media-check
ExecStart=${DOCKER_BIN} compose up -d
ExecStop=${DOCKER_BIN} compose down
TimeoutStartSec=600

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
echo "installed /etc/systemd/system/ersatztv.service"

# ── Pull and start ───────────────────────────────────────────────────────────
echo "pulling ${ETV_IMAGE} (this can take a few minutes)"
cd "$ETV_DIR"
"$DOCKER_BIN" compose pull

systemctl enable ersatztv >/dev/null 2>&1 || true
systemctl restart ersatztv

# ── Verification ─────────────────────────────────────────────────────────────
echo
echo "--- verification ---"

printf '%-28s ' "container running:"
if "$DOCKER_BIN" ps --format '{{.Names}}' | grep -qx ersatztv; then
    echo OK
else
    echo FAILED
    echo "  docker compose logs:  cd ${ETV_DIR} && ${DOCKER_BIN} compose logs --tail=50" >&2
    exit 1
fi

printf '%-28s ' "web UI on :${ETV_PORT}:"
UI_OK=0
i=0
while [ "$i" -lt 60 ]; do
    if curl -fsS -m 5 -o /dev/null "http://localhost:${ETV_PORT}/" 2>/dev/null; then
        UI_OK=1
        break
    fi
    i=$(( i + 2 ))
    sleep 2
done
if [ "$UI_OK" -eq 1 ]; then
    echo "OK (${i}s)"
else
    echo "FAILED (waited ${i}s)"
    echo "  check:  cd ${ETV_DIR} && ${DOCKER_BIN} compose logs --tail=50" >&2
    exit 1
fi

printf '%-28s ' "media visible in container:"
if [ "$("$DOCKER_BIN" exec ersatztv sh -c "ls -A '${MEDIA_PATH}' 2>/dev/null | head -1" | wc -l)" -gt 0 ]; then
    echo OK
else
    echo "FAILED — the bind mount is empty inside the container" >&2
    exit 1
fi

printf '%-28s ' "media is read-only:"
if "$DOCKER_BIN" exec ersatztv sh -c "touch '${MEDIA_PATH}/.etv_write_test' 2>/dev/null"; then
    "$DOCKER_BIN" exec ersatztv sh -c "rm -f '${MEDIA_PATH}/.etv_write_test'" || true
    echo "UNEXPECTEDLY WRITABLE — review the compose file" >&2
else
    echo "correctly denied"
fi

# Printed rather than asserted: only you know what the wall clock should say. It is here
# because a UTC container on a correct host, or a UTC host, is invisible until the watershed
# fires an hour early and unrestricted content airs before 22:00.
printf '%-28s ' "container clock:"
"$DOCKER_BIN" exec ersatztv date 2>/dev/null || echo "could not read"
echo "                             ^ must match your wall clock; dayparts are local time"

# The probe earlier only proved the device node exists. This proves ffmpeg can actually
# encode through it, which is a different question: it also covers group permissions and
# driver availability inside the container. Not fatal, but a silent CPU fallback is exactly
# the outcome the GPU was installed to avoid, so it is worth one second to find out now.
if [ -n "$ETV_DEVICES" ]; then
    printf '%-28s ' "VAAPI encode:"
    if "$DOCKER_BIN" exec ersatztv ffmpeg -hide_banner -loglevel error \
        -init_hw_device "vaapi=va:${RENDER_NODE}" \
        -f lavfi -i testsrc=d=1:s=1280x720 \
        -vf 'format=nv12,hwupload' -c:v h264_vaapi -f null - >/dev/null 2>&1; then
        echo "OK (${RENDER_NODE})"
    else
        echo "FAILED — transcoding will fall back to CPU" >&2
        echo "  the device node is present but h264_vaapi could not encode through it." >&2
        echo "  check that group_add in ${ETV_DIR}/docker-compose.yml matches its GID:" >&2
        echo "    ${DOCKER_BIN} exec ersatztv ls -l ${RENDER_NODE}" >&2
    fi
fi

printf '%-28s ' "survives reboot:"
if systemctl is-enabled ersatztv >/dev/null 2>&1; then
    echo OK
else
    echo "NOT ENABLED — run: systemctl enable ersatztv" >&2
fi

# ── Next steps ───────────────────────────────────────────────────────────────
# Resolved at runtime rather than hardcoded: the repo holds no LAN addresses, and this host
# changed once already (Plex VM -> Plex LXC) which silently invalidated every baked-in URL.
HOST_ADDR="$(hostname -I 2>/dev/null | awk '{print $1}')"
[ -n "$HOST_ADDR" ] || HOST_ADDR="$(hostname -f 2>/dev/null || hostname)"

cat <<EOF

Done. ErsatzTV is at http://${HOST_ADDR}:${ETV_PORT} (reachable from VLAN 10 via the
existing "Trusted -> Services" rule; no firewall change needed).

NEXT, IN THE ERSATZTV UI
  1. Media Sources -> Plex -> sign in. Because ${MEDIA_PATH} is identical inside and out,
     leave Path Replacements alone unless a scan reports missing files.
  2. Build a Collection, then a Schedule, then a Channel that uses them.
  3. Channels page -> set Streaming Mode. Start with MPEG-TS: Plex Live TV wants an
     HDHomeRun-style tuner and that is the mode built for it.

THEN, IN PLEX (requires an active Plex Pass)
  Settings -> Live TV & DVR -> Set Up. Point it at this host, port ${ETV_PORT}.
  XMLTV guide:  http://${HOST_ADDR}:${ETV_PORT}/iptv/xmltv.xml
  M3U playlist: http://${HOST_ADDR}:${ETV_PORT}/iptv/channels.m3u

STREAMING MODES, IF CPU LOAD OR FAN NOISE BECOMES A PROBLEM
  Transcoding only runs while someone is watching; idle channels cost nothing. If active
  viewing is too heavy, the levers are, least to most disruptive:
    - FFmpeg Profile -> turn off Normalize Video / Normalize Audio / Normalize Colors.
      Stream copies instead of re-encoding. Costs stream stability.
    - Channel -> Streaming Mode -> HLS Direct. No transcoding at all, but no watermarks,
      and some clients stumble at program boundaries. Verify Plex tolerates it.
  Both are safest if your library is uniform; mixed codecs and resolutions are exactly
  what normalization exists to paper over.

UPDATING (ErsatzTV does NOT support downgrades — back up ${ETV_DIR}/config first)
  cp -a ${ETV_DIR}/config ${ETV_DIR}/config.bak-\$(date +%F)
  cd ${ETV_DIR} && ${DOCKER_BIN} compose pull && systemctl restart ersatztv

EVERYDAY COMMANDS
  logs:     cd ${ETV_DIR} && ${DOCKER_BIN} compose logs -f
  stop:     systemctl stop ersatztv
  start:    systemctl start ersatztv

UNINSTALL
  systemctl disable --now ersatztv
  cd ${ETV_DIR} && ${DOCKER_BIN} compose down
  rm -rf ${ETV_DIR} /etc/systemd/system/ersatztv.service /usr/local/bin/ersatztv-media-check
  systemctl daemon-reload
EOF
