#!/usr/bin/env bash
#
# Copy the ErsatzTV schedules and stream selectors to the host running ErsatzTV, then VERIFY
# that what landed is byte-identical to what is in the repo.
#
# WHY THIS EXISTS
#     On 2026-10-10 a deploy appeared to succeed and did not. The `scp` step had not actually
#     transferred anything, so the follow-up `sudo install` dutifully copied whatever stale
#     copies were already sitting in /tmp. ErsatzTV then rebuilt its playouts correctly — from
#     files that were days old. Everything downstream looked like an ErsatzTV bug: a schedule
#     that would not take, two channels whose playouts "refused" to reset, a 7th Heaven
#     restriction that had no effect. An hour went into that.
#
#     The lesson is not "be careful with scp". It is that a deploy which cannot fail loudly
#     will eventually fail quietly. This script compares md5 sums after copying and exits
#     non-zero on any mismatch, so the next such failure takes ten seconds to spot.
#
# USAGE
#     scripts/deploy_ersatztv.sh user@host
#     ETV_HOST=user@host scripts/deploy_ersatztv.sh
#
#     No host is baked in, per the repo's no-addresses rule. Run from anywhere; the script
#     locates the repo relative to itself.
#
# ─── ONE PASSWORD PROMPT, NOT FOUR ───────────────────────────────────────────────
#     The first version opened a separate SSH connection for each step, so password auth asked
#     four times. This one opens a single multiplexed connection (ControlMaster) and reuses it,
#     then closes it on exit. If you would rather not type a password at all, set up key-based
#     auth yourself — this script deliberately does not touch authorized_keys.
#
# ─── WHY VERIFICATION DOES NOT USE sudo ──────────────────────────────────────────
#     The first version ran `sudo docker exec ersatztv md5sum …` to check the files as the
#     container sees them. That failed: the output is captured in a subshell, so sudo had no
#     terminal to prompt on. The files are installed mode 644 and the host directory is
#     bind-mounted straight into the container as /config, so reading them as a normal user is
#     equivalent and needs no privilege. If the plain read comes back empty — a directory that
#     a normal user cannot traverse — it retries through sudo on a real TTY and strips the
#     carriage returns a PTY adds.
#
# WHAT IT DOES NOT DO
#     It does not reset playouts and it does not refresh the Plex guide. Those are deliberate
#     actions with visible consequences for anyone currently watching, so they stay manual:
#
#         1. ErsatzTV: Scheduling -> Playouts -> Reset All Playouts
#         2. Plex:     the DVR's Refresh Guide
#
#     Copying the files alone changes nothing on air. All three steps are required.

set -euo pipefail

HOST="${1:-${ETV_HOST:-}}"
if [[ -z "$HOST" ]]; then
    echo "usage: $0 user@host   (or set ETV_HOST)" >&2
    exit 2
fi

SCHEDULES=(main.yml main-hu.yml kids.yml kids-hu.yml movies.yml movies-hu.yml)
SELECTORS=(stream-selector-en.yml stream-selector-hu.yml)

SCHED_DIR=/opt/ersatztv/config/sequential-schedules
SEL_DIR=/opt/ersatztv/config/scripts/channel-stream-selectors
STAGE=/tmp/etv-deploy

cd "$(dirname "$0")/.."
for f in "${SCHEDULES[@]}" "${SELECTORS[@]}"; do
    [[ -f "ersatztv/$f" ]] || { echo "missing: ersatztv/$f" >&2; exit 1; }
done

# md5sum is coreutils, md5 is BSD/macOS.
local_md5() {
    if command -v md5sum >/dev/null 2>&1; then md5sum "$1" | awk '{print $1}'
    else md5 -q "$1"; fi
}

CTL=$(mktemp -u "${TMPDIR:-/tmp}/etv-ssh-XXXXXX")
SSH_OPTS=(-o ControlMaster=auto -o "ControlPath=$CTL" -o ControlPersist=180)
cleanup() { ssh -O exit -o "ControlPath=$CTL" "$HOST" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "==> connecting to $HOST (one password prompt for the whole run)"
ssh "${SSH_OPTS[@]}" "$HOST" "rm -rf $STAGE && mkdir -p $STAGE"

echo "==> staging"
scp -q "${SSH_OPTS[@]}" "${SCHEDULES[@]/#/ersatztv/}" "${SELECTORS[@]/#/ersatztv/}" "$HOST:$STAGE/"

# Prove the transfer before touching anything privileged. This is the step that silently
# failed last time, and it needs no sudo.
echo "==> checking the staged copies"
staged=$(ssh "${SSH_OPTS[@]}" "$HOST" "cd $STAGE && md5sum *.yml" | tr -d '\r')
fail=0
while read -r hash f; do
    [[ -n "$f" ]] || continue
    want=$(local_md5 "ersatztv/$f")
    [[ "$hash" == "$want" ]] || { printf '    TRANSFER FAILED %-24s\n' "$f"; fail=1; }
done <<< "$staged"
[[ $(grep -c . <<< "$staged") -eq $(( ${#SCHEDULES[@]} + ${#SELECTORS[@]} )) ]] || {
    echo "    expected $(( ${#SCHEDULES[@]} + ${#SELECTORS[@]} )) staged files, found $(grep -c . <<< "$staged")"
    fail=1
}
[[ $fail -eq 0 ]] || { echo; echo "scp did not deliver what it should have. Nothing installed." >&2; exit 1; }
echo "    all $(( ${#SCHEDULES[@]} + ${#SELECTORS[@]} )) files staged correctly"

# A fresh install has neither target folder, and an LXC logged into as root often has no sudo.
echo "==> installing"
ssh -t "${SSH_OPTS[@]}" "$HOST" "S=; [ \"\$(id -u)\" -eq 0 ] || S=sudo; \
 \$S mkdir -p $SCHED_DIR $SEL_DIR \
 && \$S install -m 644 $(printf "$STAGE/%s " "${SCHEDULES[@]}") $SCHED_DIR/ \
 && \$S install -m 644 $(printf "$STAGE/%s " "${SELECTORS[@]}") $SEL_DIR/ \
 && \$S rm -f $SCHED_DIR/stream-selector-en.yml $SCHED_DIR/stream-selector-hu.yml"

echo "==> verifying what is on disk"
paths=$(printf "$SCHED_DIR/%s " "${SCHEDULES[@]}"; printf "$SEL_DIR/%s " "${SELECTORS[@]}")
remote=$(ssh "${SSH_OPTS[@]}" "$HOST" "md5sum $paths 2>/dev/null" | tr -d '\r' || true)
if [[ -z "${remote//[[:space:]]/}" ]]; then
    echo "    (not readable unprivileged, retrying with sudo on a tty)"
    remote=$(ssh -t "${SSH_OPTS[@]}" "$HOST" "sudo md5sum $paths" | tr -d '\r')
fi

fail=0
found=0
while read -r hash path; do
    [[ -n "$path" ]] || continue
    f=$(basename "$path")
    [[ "$f" == *.yml ]] || continue
    want=$(local_md5 "ersatztv/$f")
    found=$((found + 1))
    if [[ "$hash" == "$want" ]]; then
        printf '    ok    %-26s %s\n' "$f" "$hash"
    else
        printf '    STALE %-26s on disk %s, repo %s\n' "$f" "$hash" "$want"
        fail=1
    fi
done <<< "$remote"

if [[ $found -ne $(( ${#SCHEDULES[@]} + ${#SELECTORS[@]} )) ]]; then
    echo "    only verified $found of $(( ${#SCHEDULES[@]} + ${#SELECTORS[@]} )) files" >&2
    fail=1
fi

if [[ $fail -ne 0 ]]; then
    echo
    echo "DEPLOY FAILED — at least one file on disk does not match the repo." >&2
    echo "Do NOT reset playouts; they would rebuild from the stale file." >&2
    exit 1
fi

cat <<'DONE'

All files match. Two manual steps remain, and skipping either leaves stale programming:

  1. ErsatzTV  Scheduling -> Playouts -> Reset All Playouts
                (required whenever content sources change, not just times)
  2. Plex      the DVR's Refresh Guide

Then open a playout and confirm it lists concrete programmes with times. An empty playout
means a query matched nothing, and ErsatzTV flags failed builds in yellow.
DONE
