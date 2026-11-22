#!/usr/bin/env bash
# Build ersatztv:<version> from the public GitHub forks on this host.
# Expects env from /opt/ersatztv/local/env (see deploy/local.example/env).
#
# .NET publish runs on the host when `dotnet` is installed; otherwise it runs
# inside the official SDK container so an LXC without a host SDK still works.
set -euo pipefail

die() { echo "error: $*" >&2; exit 1; }

: "${ETV_IMAGE:?}"
: "${LEGACY_TAG:?}"
: "${ETV_REPO:?}"
: "${ETV_BRANCH:?}"
: "${NEXT_REPO:?}"
: "${NEXT_BRANCH:?}"
: "${DEPLOY_DIR:?}"
: "${ETV_DIR:?}"

BUILD_ROOT="${ETV_DIR}/build"
SRC_ETV="${BUILD_ROOT}/ersatztv"
SRC_NEXT="${BUILD_ROOT}/ersatztv-next"
CACHE="${ETV_DIR}/.build-cache"
WORKDIR="${BUILD_ROOT}/work"
SKIP_UNCHANGED_BUILD="${SKIP_UNCHANGED_BUILD:-1}"
DOTNET_SDK_IMAGE="${DOTNET_SDK_IMAGE:-mcr.microsoft.com/dotnet/sdk:10.0-noble}"

export DOTNET_CLI_TELEMETRY_OPTOUT=1

command -v docker >/dev/null || die "docker is required"
command -v git >/dev/null || die "git is required"

mkdir -p "$BUILD_ROOT" "$CACHE"

clone_or_update() {
    repo=$1 branch=$2 dir=$3
    if [ -d "$dir/.git" ]; then
        echo "==> updating $(basename "$dir") ($branch)"
        git -C "$dir" fetch -q --tags origin
        git -C "$dir" checkout -q "$branch"
        git -C "$dir" reset -q --hard "origin/$branch"
    else
        echo "==> cloning $repo ($branch)"
        git clone -q --branch "$branch" --single-branch "$repo" "$dir"
    fi
}

clone_or_update "$ETV_REPO" "$ETV_BRANCH" "$SRC_ETV"
clone_or_update "$NEXT_REPO" "$NEXT_BRANCH" "$SRC_NEXT"

if git -C "$SRC_ETV" rev-parse -q --verify "$LEGACY_TAG^{commit}" >/dev/null; then
    if ! git -C "$SRC_ETV" merge-base --is-ancestor "$LEGACY_TAG" HEAD; then
        echo "warning: ${LEGACY_TAG} is not an ancestor of ${ETV_BRANCH}; building HEAD anyway" >&2
    fi
fi

NEXT_TAG=$(git -C "$SRC_ETV" show "HEAD:.github/next-tag" 2>/dev/null | tr -d '[:space:]' || true)
[ -n "$NEXT_TAG" ] || NEXT_TAG=$(git -C "$SRC_NEXT" describe --tags --abbrev=0 2>/dev/null || echo unknown)

ETV_SHA=$(git -C "$SRC_ETV" rev-parse --short HEAD)
NEXT_SHA=$(git -C "$SRC_NEXT" rev-parse --short HEAD)
VERSION="${LEGACY_TAG}-fork.${ETV_SHA}"
STATE="${ETV_SHA}:${NEXT_SHA}:${LEGACY_TAG}"

if [ "$SKIP_UNCHANGED_BUILD" = "1" ] && [ -f "$CACHE/last-state" ] \
    && [ "$(cat "$CACHE/last-state")" = "$STATE" ] \
    && docker image inspect "$ETV_IMAGE" >/dev/null 2>&1; then
    echo "==> image already built for $STATE — skipping build"
    echo "$VERSION" > "$CACHE/last-version"
    exit 0
fi

echo "==> preparing publish tree for $VERSION"
rm -rf "$WORKDIR"
mkdir -p "$WORKDIR/ctx/app" "$WORKDIR/src"
git -C "$SRC_ETV" archive HEAD | tar -x -C "$WORKDIR/src"
if [ -f "$WORKDIR/src/ErsatzTV/ErsatzTV.csproj" ]; then
    # Match upstream docker packaging.
    sed -i '/Scanner/d' "$WORKDIR/src/ErsatzTV/ErsatzTV.csproj" 2>/dev/null \
        || sed -i '' '/Scanner/d' "$WORKDIR/src/ErsatzTV/ErsatzTV.csproj"
fi

publish_one() {
    proj=$1
    [ -f "$WORKDIR/src/$proj" ] || die "missing $proj in fork checkout"
    if command -v dotnet >/dev/null 2>&1; then
        export PATH="${HOME}/.dotnet:${PATH:-}"
        [ -d "${HOME}/.dotnet" ] && export DOTNET_ROOT="${HOME}/.dotnet"
        dotnet publish "$WORKDIR/src/$proj" -c release -o "$WORKDIR/ctx/app" -r linux-x64 \
            --self-contained false -nologo -v quiet \
            /p:DebugType=Embedded /p:InformationalVersion="$VERSION"
    else
        echo "    (dotnet SDK via ${DOTNET_SDK_IMAGE})"
        docker run --rm \
            -v "$WORKDIR/src:/src:ro" \
            -v "$WORKDIR/ctx/app:/out" \
            -e DOTNET_CLI_TELEMETRY_OPTOUT=1 \
            "$DOTNET_SDK_IMAGE" \
            dotnet publish "/src/$proj" -c release -o /out -r linux-x64 \
                --self-contained false -nologo -v quiet \
                /p:DebugType=Embedded /p:InformationalVersion="$VERSION"
    fi
}

echo "==> publishing Scanner + ErsatzTV for linux-x64"
publish_one ErsatzTV.Scanner/ErsatzTV.Scanner.csproj
publish_one ErsatzTV/ErsatzTV.csproj

if [ -d "$WORKDIR/src/scripts/scripted-schedules" ]; then
    cp -R "$WORKDIR/src/scripts/scripted-schedules" "$WORKDIR/ctx/scripted-schedules"
else
    mkdir -p "$WORKDIR/ctx/scripted-schedules"
fi
cp "${DEPLOY_DIR}/deploy/build/Dockerfile" "$WORKDIR/ctx/Dockerfile"

CHANNEL_BIN="${CACHE}/ersatztv-channel"
CHANNEL_SHA_FILE="${CACHE}/ersatztv-channel.sha"
if [ -x "$CHANNEL_BIN" ] && [ "$(cat "$CHANNEL_SHA_FILE" 2>/dev/null || true)" = "$NEXT_SHA" ]; then
    echo "==> ersatztv-channel $NEXT_SHA already built, reusing"
else
    echo "==> building ersatztv-channel (next $NEXT_SHA / $NEXT_TAG)"
    DOCKER_BUILDKIT=1 docker build -f "$SRC_NEXT/docker/Dockerfile" --target build \
        --build-arg INFO_VERSION="${NEXT_TAG}-fork.${NEXT_SHA}" \
        --build-arg ETV_COMMIT="$NEXT_SHA" \
        -t "ersatztv-next-build:fork" "$SRC_NEXT"
    id=$(docker create ersatztv-next-build:fork)
    docker cp "$id:/out/ersatztv-channel" "$CHANNEL_BIN"
    docker rm "$id" >/dev/null
    chmod +x "$CHANNEL_BIN"
    echo "$NEXT_SHA" > "$CHANNEL_SHA_FILE"
fi
cp "$CHANNEL_BIN" "$WORKDIR/ctx/ersatztv-channel"

echo "==> assembling ${ETV_IMAGE} and ersatztv:${VERSION}"
DOCKER_BUILDKIT=1 docker build \
    --build-arg "LEGACY_TAG=${LEGACY_TAG}" \
    -t "$ETV_IMAGE" \
    -t "ersatztv:${VERSION}" \
    "$WORKDIR/ctx"

echo "$STATE" > "$CACHE/last-state"
echo "$VERSION" > "$CACHE/last-version"
rm -rf "$WORKDIR"

echo
echo "done: ${ETV_IMAGE} (also ersatztv:${VERSION})"
docker image ls --format 'table {{.Repository}}:{{.Tag}}\t{{.ID}}\t{{.CreatedSince}}' | head -5
