#!/usr/bin/env bash
# Build ersatztv:<version> from upstream tags + patches in this single public repo.
# Expects env from /opt/ersatztv/local/env (and versions.env from the deploy checkout).
set -euo pipefail

die() { echo "error: $*" >&2; exit 1; }

: "${ETV_IMAGE:?}"
: "${DEPLOY_DIR:?}"
: "${ETV_DIR:?}"

# Repo pins (versions.env) with optional local/env overrides already sourced by update.sh.
VERSIONS="${DEPLOY_DIR}/versions.env"
[ -f "$VERSIONS" ] || die "missing ${VERSIONS}"
# shellcheck disable=SC1090
set -a
# shellcheck disable=SC1091
. "$VERSIONS"
set +a

: "${LEGACY_TAG:?}"
: "${NEXT_TAG:?}"
: "${LEGACY_UPSTREAM:?}"
: "${NEXT_UPSTREAM:?}"

BUILD_ROOT="${ETV_DIR}/build"
SRC_ETV="${BUILD_ROOT}/ersatztv"
SRC_NEXT="${BUILD_ROOT}/ersatztv-next"
CACHE="${ETV_DIR}/.build-cache"
WORKDIR="${BUILD_ROOT}/work"
SKIP_UNCHANGED_BUILD="${SKIP_UNCHANGED_BUILD:-1}"
DOTNET_SDK_IMAGE="${DOTNET_SDK_IMAGE:-mcr.microsoft.com/dotnet/sdk:10.0-noble}"
PATCH_LEGACY="${DEPLOY_DIR}/patches/legacy"
PATCH_NEXT="${DEPLOY_DIR}/patches/next"

export DOTNET_CLI_TELEMETRY_OPTOUT=1

command -v docker >/dev/null || die "docker is required"
command -v git >/dev/null || die "git is required"

mkdir -p "$BUILD_ROOT" "$CACHE"

checkout_upstream() {
    url=$1 tag=$2 dir=$3
    if [ -d "$dir/.git" ]; then
        echo "==> updating $(basename "$dir") to ${tag}"
        git -C "$dir" remote set-url origin "$url"
        git -C "$dir" fetch -q --tags --force origin "refs/tags/${tag}:refs/tags/${tag}"
        git -C "$dir" checkout -q -f "$tag"
        # Annotated tags: resolve to the commit they point at.
        git -C "$dir" reset -q --hard "refs/tags/${tag}^{commit}" 2>/dev/null \
            || git -C "$dir" reset -q --hard "$tag"
        # Drop any previous patch commits / dirty state before re-applying.
        git -C "$dir" clean -fdq
        git -C "$dir" am --abort >/dev/null 2>&1 || true
    else
        echo "==> cloning ${url} @ ${tag}"
        git clone -q --branch "$tag" --single-branch "$url" "$dir"
        git -C "$dir" reset -q --hard "refs/tags/${tag}^{commit}" 2>/dev/null \
            || git -C "$dir" reset -q --hard "$tag"
    fi
}

apply_patches() {
    dir=$1 patch_dir=$2 label=$3
    shopt -s nullglob
    patches=("$patch_dir"/*.patch)
    shopt -u nullglob
    if [ ${#patches[@]} -eq 0 ]; then
        echo "==> no ${label} patches"
        return
    fi
    echo "==> applying ${#patches[@]} ${label} patch(es)"
    git -C "$dir" am --3way "${patches[@]}"
}

patch_fingerprint() {
    # Stable id of the patch set so SKIP_UNCHANGED_BUILD can detect edits.
    if command -v sha256sum >/dev/null 2>&1; then
        find "$1" -type f -name '*.patch' -print0 | sort -z | xargs -0 sha256sum | sha256sum | awk '{print $1}'
    else
        find "$1" -type f -name '*.patch' -print0 | sort -z | xargs -0 shasum -a 256 | shasum -a 256 | awk '{print $1}'
    fi
}

checkout_upstream "$LEGACY_UPSTREAM" "$LEGACY_TAG" "$SRC_ETV"
checkout_upstream "$NEXT_UPSTREAM" "$NEXT_TAG" "$SRC_NEXT"
apply_patches "$SRC_ETV" "$PATCH_LEGACY" legacy
apply_patches "$SRC_NEXT" "$PATCH_NEXT" next

ETV_SHA=$(git -C "$SRC_ETV" rev-parse --short HEAD)
NEXT_SHA=$(git -C "$SRC_NEXT" rev-parse --short HEAD)
VERSION="${LEGACY_TAG}-improve.${ETV_SHA}"
FP_LEGACY=$(patch_fingerprint "$PATCH_LEGACY")
FP_NEXT=$(patch_fingerprint "$PATCH_NEXT")
STATE="${LEGACY_TAG}:${NEXT_TAG}:${FP_LEGACY}:${FP_NEXT}:${ETV_SHA}:${NEXT_SHA}"

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
    sed -i '/Scanner/d' "$WORKDIR/src/ErsatzTV/ErsatzTV.csproj" 2>/dev/null \
        || sed -i '' '/Scanner/d' "$WORKDIR/src/ErsatzTV/ErsatzTV.csproj"
fi

publish_one() {
    proj=$1
    [ -f "$WORKDIR/src/$proj" ] || die "missing $proj after patches"
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
        --build-arg INFO_VERSION="${NEXT_TAG}-improve.${NEXT_SHA}" \
        --build-arg ETV_COMMIT="$NEXT_SHA" \
        -t "ersatztv-next-build:improve" "$SRC_NEXT"
    id=$(docker create ersatztv-next-build:improve)
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
