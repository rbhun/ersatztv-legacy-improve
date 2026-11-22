# Runtime image for the public fork. .NET app is published into ./app ahead of time;
# ersatztv-channel is copied in by build-image.sh after the Next Docker build.
ARG FFMPEG_IMAGE=ghcr.io/ersatztv/ersatztv-ffmpeg:8.1.2-9@sha256:689c158305c2456a230f002539b47499841cee0d237975ed30ee6a9b119bb9a5
ARG LEGACY_TAG=v26.13.0

FROM mcr.microsoft.com/dotnet/aspnet:10.0.13-noble-amd64@sha256:f879b8a9cb3f6694b8b0c9fa530eb0c39d8920db09c05a7edbd6c4c6c104ae1b AS dotnet-runtime

FROM ghcr.io/ersatztv/legacy:${LEGACY_TAG} AS legacy

FROM ${FFMPEG_IMAGE}
COPY --from=dotnet-runtime /usr/share/dotnet /usr/share/dotnet
RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 && \
    apt-get clean -y && \
    rm -rf /var/lib/apt/lists/*
COPY --from=legacy /app/pythonlibs /app/pythonlibs
ENV FONTCONFIG_PATH=/etc/fonts
RUN fc-cache update
WORKDIR /app
COPY scripted-schedules/ ./scripted-schedules/
COPY app/ ./
COPY ersatztv-channel ./
RUN chmod +x ErsatzTV ErsatzTV.Scanner ersatztv-channel
ENV PYTHONPATH=/app/pythonlibs
ENV ETV_CONFIG_FOLDER=/config
ENV ETV_TRANSCODE_FOLDER=/transcode
ENTRYPOINT ["./ErsatzTV"]
