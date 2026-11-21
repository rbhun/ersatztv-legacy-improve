#!/bin/sh
# install_kometa.sh – Install Kometa (was Plex Meta Manager) as a Docker container
#
# Runs on EITHER the NAS LXC (alongside the *arr stack) or the Plex VM. Kometa never opens a
# media file — it is purely a Plex API client — so it does not need to live where the media
# is. What it does need is outbound internet for TMDb and MDBList, and a route to Plex.
#
#   sudo sh install_kometa.sh
#
# Over SSH, allocate a TTY or sudo cannot prompt for the password:
#   scp install_kometa.sh <host>:/tmp/
#   ssh -t <host> 'sudo sh /tmp/install_kometa.sh'
#
# Options:
#   --plex-url URL          where Plex lives; auto-detected if omitted
#   --force                 skip the reachability pre-flight checks
#   --enable-genre-update   also overwrite every genre from TMDb (READ THE WARNING BELOW)
#
# HOST CHOICE
#   The NAS LXC is the better home if it has WAN access, because the Plex VM is the host
#   under CPU pressure — it runs Plex plus ErsatzTV, which transcodes on CPU only. Kometa is
#   light but not free, and a weekly run has no reason to compete for that CPU.
#
#   Two things to confirm on the NAS LXC before trusting it:
#     - Outbound internet. Firewall rule 11 blocks VLAN 30 from WAN except the hosts listed
#       in rule 10. If .4 is not in rule 10, Kometa cannot reach TMDb and will not start at
#       all, since the TMDb key is mandatory. The pre-flight check below catches this.
#     - Docker inside an LXC needs nesting enabled on the container.
#
# WHAT THIS IS FOR
#   The library audit found metadata that is inconsistent rather than absent. The one field
#   that is actively unusable is the content rating: Plex holds Hungarian certificates
#   (hu/16, hu/12, hu/KN, hu/6, hu/14, hu/18), which ErsatzTV can match only as opaque
#   case-sensitive strings. Kometa can rewrite them all from one source, which turns
#   content_rating into a field you can actually schedule against — a real age gate for the
#   kids channel instead of inferring safety from genre.
#
# WHY GENRE UPDATING IS OFF BY DEFAULT
#   `mass_genre_update: tmdb` does not fill blanks. It REPLACES every genre on every item,
#   and this library's genres are richer than TMDb's fixed vocabulary. Enabling it destroys,
#   on the movie side: biography (33 films), musical (19), short (4), children (3), sport (2).
#   On the TV side TMDb uses compound genres ("Action & Adventure", "Sci-Fi & Fantasy") and
#   11 of the 17 genres currently in use would be lost.
#
#   It also would not fix the titles that actually lack a genre. Those 12 films and 1 show are
#   UNMATCHED in Plex — no GUID — so Kometa has nothing to look them up by. Fix the match and
#   Plex's own agent fills the genres itself, in the richer vocabulary. Kometa is the wrong
#   tool for that job.
#
# THIS SCRIPT DOES NOT TOUCH YOUR LIBRARY. It installs and configures only. The first run is
# deliberately manual so you can watch what it does before letting a timer loose on it.

set -eu

KOMETA_DIR=/opt/kometa
CONFIG_DIR="${KOMETA_DIR}/config"
IMAGE=kometateam/kometa:latest
PLEX_PORT=32400

FORCE=0
ENABLE_GENRE=0
PLEX_URL=""

while [ $# -gt 0 ]; do
    case "$1" in
        --force) FORCE=1 ;;
        --enable-genre-update) ENABLE_GENRE=1 ;;
        --plex-url)
            shift
            [ $# -gt 0 ] || { echo "ERROR: --plex-url needs a value" >&2; exit 2; }
            PLEX_URL="$1"
            ;;
        --plex-url=*) PLEX_URL="${1#*=}" ;;
        -h|--help)
            echo "usage: sudo sh $0 [--plex-url URL] [--force] [--enable-genre-update]"
            exit 0
            ;;
        *) echo "ERROR: unknown argument '$1' (try --help)" >&2; exit 2 ;;
    esac
    shift
done

# ── Re-exec under sudo ───────────────────────────────────────────────────────────
# Flags are re-passed explicitly rather than exported, because a sudoers policy may
# refuse to carry environment variables across.
if [ "$(id -u)" -ne 0 ]; then
    if ! command -v sudo >/dev/null 2>&1; then
        echo "ERROR: not root and sudo is not installed." >&2
        exit 1
    fi
    if [ ! -f "$0" ]; then
        echo "ERROR: cannot re-exec; run this from a file, not a pipe." >&2
        exit 1
    fi
    if ! sudo -n true 2>/dev/null && [ ! -t 0 ]; then
        echo "ERROR: sudo needs a password but there is no terminal to prompt on." >&2
        echo "       Re-run with a TTY:  ssh -t <plex-vm> 'sudo sh $0'" >&2
        exit 1
    fi
    set -- ""
    [ "$FORCE" = "1" ] && set -- "$@" --force
    [ "$ENABLE_GENRE" = "1" ] && set -- "$@" --enable-genre-update
    [ -n "$PLEX_URL" ] && set -- "$@" --plex-url "$PLEX_URL"
    shift                                  # drop the placeholder
    exec sudo sh "$0" "$@"
fi

# ── Refuse to run on the Proxmox host ───────────────────────────────────────────
if [ -d /etc/pve ] || command -v qm >/dev/null 2>&1 || command -v pct >/dev/null 2>&1; then
    echo "ERROR: this looks like the Proxmox host, not the Plex VM. Refusing." >&2
    exit 1
fi

# ── Locate Plex ─────────────────────────────────────────────────────────────────
# /identity needs no token, so it is a clean reachability probe. A container cannot use the
# host's 127.0.0.1, so when Plex turns out to be local the compose file gets a host-gateway
# alias instead; when it is remote the hostname is used directly and no alias is needed.
PLEX_IS_LOCAL=0
if [ -n "$PLEX_URL" ]; then
    echo "using Plex URL as given: ${PLEX_URL}"
elif curl -fsS --max-time 5 "http://127.0.0.1:${PLEX_PORT}/identity" >/dev/null 2>&1; then
    PLEX_IS_LOCAL=1
    PLEX_URL="http://host.docker.internal:${PLEX_PORT}"
    echo "Plex found on this host; container will reach it via the Docker host gateway"
elif curl -fsS --max-time 5 "http://plex.internal:${PLEX_PORT}/identity" >/dev/null 2>&1; then
    PLEX_URL="http://plex.internal:${PLEX_PORT}"
    echo "Plex found at plex.internal"
else
    echo "ERROR: could not find Plex on 127.0.0.1 or at plex.internal:${PLEX_PORT}." >&2
    echo "       Pass it explicitly, e.g.  --plex-url http://plex.internal:${PLEX_PORT}" >&2
    exit 1
fi

# ── Pre-flight: outbound internet ───────────────────────────────────────────────
# This is the check that matters on the NAS LXC. Firewall rule 11 blocks VLAN 30 from WAN
# unless the host is listed in rule 10, and Kometa refuses to start without TMDb, so a
# blocked host fails in a way that looks like a bad API key rather than a firewall.
if [ "$FORCE" = "0" ]; then
    for endpoint in api.themoviedb.org api.mdblist.com; do
        if curl -fsS --max-time 8 -o /dev/null "https://${endpoint}/" 2>/dev/null \
            || curl -fsS --max-time 8 -o /dev/null "https://${endpoint}" 2>/dev/null; then
            echo "outbound OK: ${endpoint}"
        else
            # A 4xx still proves the host is routable; only a connection failure is fatal.
            if curl -s --max-time 8 -o /dev/null -w '' "https://${endpoint}/" 2>/dev/null; then
                echo "outbound OK: ${endpoint} (answered, non-2xx as expected)"
            else
                echo "ERROR: cannot reach ${endpoint} from this host." >&2
                echo "       Kometa cannot run without TMDb. If this is the NAS LXC, it is" >&2
                echo "       almost certainly firewall rule 11 blocking VLAN 30 from WAN —" >&2
                echo "       add this host to the rule 10 whitelist, or install on a host" >&2
                echo "       that already has WAN access. Override with --force." >&2
                exit 1
            fi
        fi
    done
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: docker is not installed." >&2
    echo "       Run install_ersatztv_plex_vm.sh first; it installs Docker CE + compose." >&2
    exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
    echo "ERROR: the docker compose plugin is missing." >&2
    exit 1
fi

# ── Collect credentials without ever printing them ──────────────────────────────
# Read from the invoking user's home, not root's, since sudo changes $HOME.
if [ -n "${SUDO_USER:-}" ]; then
    USER_HOME="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
else
    USER_HOME="${HOME}"
fi

read_secret() {
    _path="${USER_HOME}/$1"
    if [ ! -f "$_path" ]; then
        echo "ERROR: missing ${_path}" >&2
        echo "       $2" >&2
        echo "       Create it with:  printf %s 'THEKEY' > ${_path} && chmod 600 ${_path}" >&2
        return 1
    fi
    tr -d ' \t\r\n' < "$_path"
}

echo "reading credentials from ${USER_HOME} (values are never echoed)"
PLEX_TOKEN="$(read_secret .plex_token \
    'Plex token: any Plex web URL contains X-Plex-Token=...')"
TMDB_KEY="$(read_secret .tmdb_key \
    'TMDb API key (free): themoviedb.org -> Settings -> API. Kometa requires this.')"
MDBLIST_KEY="$(read_secret .mdblist_key \
    'MDBList API key (free): mdblist.com/preferences. Needed for Common Sense ratings.')"

for pair in "PLEX_TOKEN:${PLEX_TOKEN}" "TMDB_KEY:${TMDB_KEY}" "MDBLIST_KEY:${MDBLIST_KEY}"; do
    if [ -z "${pair#*:}" ]; then
        echo "ERROR: ${pair%%:*} file exists but is empty." >&2
        exit 1
    fi
done

mkdir -p "${CONFIG_DIR}"
chmod 700 "${KOMETA_DIR}" "${CONFIG_DIR}"

# ── config.yml ──────────────────────────────────────────────────────────────────
# Kometa reaches Plex through the Docker host gateway rather than host networking, so the
# container gets no broader access to the VM than it needs. This also keeps the file free
# of any hard-coded address.
if [ "$ENABLE_GENRE" = "1" ]; then
    GENRE_LINE='      mass_genre_update: tmdb'
    echo
    echo "WARNING: --enable-genre-update will REPLACE every genre from TMDb."
    echo "         biography, musical, short, children and sport will be erased from the"
    echo "         movie library, and 11 of 17 TV genres will be lost. The ErsatzTV"
    echo "         schedules query genre, so re-run the audit and re-tune them afterwards."
    echo
else
    GENRE_LINE='      # mass_genre_update: tmdb   # DISABLED -- see header; this overwrites, not fills'
fi

cat > "${CONFIG_DIR}/config.yml" <<EOF
## Kometa configuration -- generated by install_kometa_plex_vm.sh
##
## Only 'operations' are configured. No collection files are defined, so Kometa will log
## "No Collection File(s) Found" for each library and then carry on with the operations,
## which is the intended behaviour here.
##
## mass_content_rating_update is the operation that earns its keep: it replaces the
## Hungarian certificates (hu/16, hu/12, hu/KN, ...) with Common Sense Media age numbers
## from one consistent source, so ErsatzTV can schedule against content_rating instead of
## inferring safety from genre. Values arrive as plain numbers such as 10 or 13, which are
## easy to enumerate in a query:
##     type:movie AND (content_rating:0 OR content_rating:3 OR content_rating:6)
## Swap in mdb_commonsense_nice for "13+" style, or omdb for MPAA style (G/PG/PG-13/R),
## which needs an OMDb key and is capped at 1000 lookups a day.

libraries:
  Movies:
    operations:
${GENRE_LINE}
      mass_content_rating_update: mdb_commonsense
  TV Series:
    operations:
${GENRE_LINE}
      mass_content_rating_update: mdb_commonsense
  Cartoons:
    operations:
${GENRE_LINE}
      mass_content_rating_update: mdb_commonsense
  Animated:
    operations:
${GENRE_LINE}
      mass_content_rating_update: mdb_commonsense

## 'Demos' and 'Other videos' are deliberately absent. They hold drone footage and TV
## demo loops, nothing Kometa can or should label.

settings:
  cache: true
  cache_expiration: 60
  run_again_delay: 0
  save_report: true
  show_unmanaged: false
  show_unconfigured: false
  ## Leave existing values alone where the source has nothing to offer, rather than
  ## blanking a field that currently holds something.
  tvdb_language: eng

plex:
  url: ${PLEX_URL}
  token: ${PLEX_TOKEN}
  timeout: 60
  clean_bundles: false
  empty_trash: false
  optimize: false

tmdb:
  apikey: ${TMDB_KEY}
  language: en
  cache_expiration: 60

mdblist:
  apikey: ${MDBLIST_KEY}
  cache_expiration: 60
EOF
chmod 600 "${CONFIG_DIR}/config.yml"
echo "wrote ${CONFIG_DIR}/config.yml (0600 — it holds your Plex token and API keys)"

# ── docker-compose.yml ──────────────────────────────────────────────────────────
cat > "${KOMETA_DIR}/docker-compose.yml" <<EOF
services:
  kometa:
    image: ${IMAGE}
    container_name: kometa
    # No restart policy and no internal scheduler: this container is invoked on demand by
    # kometa-run, so it is never sitting idle holding a Plex connection open.
    restart: "no"
    environment:
      TZ: \${TZ:-Europe/Budapest}
    volumes:
      - ${CONFIG_DIR}:/config
EOF

# Only needed when Plex is on this same host; a remote Plex is reached by hostname.
if [ "$PLEX_IS_LOCAL" = "1" ]; then
    cat >> "${KOMETA_DIR}/docker-compose.yml" <<'EOF'
    extra_hosts:
      - "host.docker.internal:host-gateway"
EOF
fi
echo "wrote ${KOMETA_DIR}/docker-compose.yml (plex url: ${PLEX_URL})"

# ── kometa-run helper ───────────────────────────────────────────────────────────
cat > /usr/local/bin/kometa-run <<EOF
#!/bin/sh
# kometa-run [kometa args...] – run Kometa once, in the foreground.
#
#   kometa-run --libraries Animated   try it on the 4-item library first
#   kometa-run                        all four libraries
#
# Logs land in ${CONFIG_DIR}/logs/meta.log
set -eu
cd ${KOMETA_DIR}
exec docker compose run --rm kometa --run --read-only-config "\$@"
EOF
chmod 755 /usr/local/bin/kometa-run
echo "installed /usr/local/bin/kometa-run"

# ── Weekly timer, installed but NOT enabled ─────────────────────────────────────
cat > /etc/systemd/system/kometa.service <<EOF
[Unit]
Description=Kometa metadata normalisation for Plex
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/kometa-run
EOF

cat > /etc/systemd/system/kometa.timer <<'EOF'
[Unit]
Description=Run Kometa weekly

[Timer]
OnCalendar=Sun 04:30
Persistent=true
RandomizedDelaySec=15m

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
echo "installed kometa.service + kometa.timer (NOT enabled — see next steps)"

# ── Verify ──────────────────────────────────────────────────────────────────────
echo "pulling ${IMAGE} ..."
docker pull "${IMAGE}" >/dev/null
echo "image present: $(docker image inspect "${IMAGE}" --format '{{.Id}}' | cut -c1-19)"

if command -v python3 >/dev/null 2>&1; then
    if python3 -c 'import yaml,sys; yaml.safe_load(open(sys.argv[1]))' \
        "${CONFIG_DIR}/config.yml" 2>/dev/null; then
        echo "config.yml parses as valid YAML"
    else
        echo "WARNING: could not parse config.yml as YAML (python3-yaml may be absent)" >&2
    fi
fi

cat <<EOF

Done. Nothing in Plex has been changed yet. Plex will be reached at ${PLEX_URL}

MIND THE QUOTA: a free MDBList key allows 1000 requests a day, and a full run needs about
840 — one per movie and one per show. That fits, with little to spare, so do not spend the
day's allowance experimenting. Caching is on with a 60-day expiry, so repeat runs are cheap.

NEXT STEPS, in this order:

  1. Canary run on the smallest library. Four items, so four requests:
         sudo kometa-run --libraries Animated

     Then check one of those films in Plex. Its content rating should have changed from
     a hu/... value to a plain number.

  2. If that looks right, do the whole lot. Expect 10-20 minutes:
         sudo kometa-run

  3. Re-run the library audit from your workstation to see the new vocabulary, then the
     kids-channel queries can gain a real age gate instead of trusting genre:
         python3 scripts/plex_library_audit.py

  4. Only once you are happy, let it keep itself tidy weekly:
         sudo systemctl enable --now kometa.timer

TO UNDO a content-rating run, set mass_content_rating_update to 'reset' in
${CONFIG_DIR}/config.yml and run again; Plex re-reads the value from its own agent.
EOF
