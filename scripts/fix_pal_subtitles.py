#!/usr/bin/env python3
"""Rescale external subtitles that were timed for the 23.976 fps cut of a 25 fps file.

WHY THIS EXISTS
    ErsatzTV burns subtitles into the picture, so a mistimed subtitle ruins the
    programme and the viewer cannot switch it off. Plex, on the same file, looks fine --
    which for a long time made this look like an ErsatzTV bug. It is not. Plex analyses
    the audio for speech (`hasVoiceActivity: 1`) and realigns the subtitle at playback
    (`canAutoSync: 1`). That correction lives in Plex's playback layer, never in the
    file, so ErsatzTV reading the `.srt` off disk gets the uncorrected timings.

    This writes the correction into the file, which is the only form ErsatzTV can see.
    Plex is unaffected: once the file is right there is nothing left for it to correct.

WHAT IT CHANGES, AND WHAT IT REFUSES TO
    A subtitle timed for the 23.976 fps master of a film you hold as a 25 fps PAL
    encode runs exactly 25/23.976 = 1.04271 times too long. That is a specific,
    falsifiable claim about a file, and it is the only case this touches: every
    timestamp is multiplied by 23.976/25 = 0.95904, a constant, never a figure fitted
    to the file.

    Subtitles that overrun by some other amount belong to a different cut of the
    programme. Rescaling those would produce something that is wrong in a new way
    rather than wrong in the old way, so they are reported and skipped. Across this
    library the deviation from the PAL constant has a median of 0.57%, which on a
    110-minute film is 38 seconds -- so most overrunning subtitles are NOT this bug,
    and the default tolerance is deliberately tight.

HOW IT AVOIDS DAMAGING ANYTHING
    - Dry run unless --apply is passed.
    - The original is copied to `<name>.srt.orig` first, and a file that already has one
      is skipped, so re-running cannot rescale twice.
    - Rewriting happens on BYTES, and only on lines that are a complete cue-timing line.
      Subtitle text is never decoded, so Windows-1250 and ISO-8859-2 files (most of the
      Hungarian ones) cannot be mangled by an encoding round-trip.
    - After writing, it re-reads from disk and checks two things: that the last cue now
      lands on the final frame, and that every byte outside the timing lines is
      unchanged. Either check failing restores the backup.

RUNNING IT
    This has to run on the Plex VM, because Plex's API does not expose the on-disk path
    of an external subtitle -- only `/library/streams/{id}` -- so the files can only be
    found by looking next to the video. Durations come from ffprobe inside the ErsatzTV
    container, which is the same binary ErsatzTV transcodes with.

        python3 fix_pal_subtitles.py --path "/mnt/media/Movies/Meet the Fockers (2004)"
        python3 fix_pal_subtitles.py --path "/mnt/media/Movies/Meet the Fockers (2004)" --apply
        python3 fix_pal_subtitles.py --path /mnt/media/Movies          # the whole library
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import shlex
import shutil
import subprocess
import sys

PAL_NTSC = 25 / 23.976        # 1.042709...  how much too long such a subtitle runs
SCALE = 23.976 / 25           # 0.95904      the correction, exact and constant

VIDEO_EXT = {".avi", ".mkv", ".mp4", ".mpg", ".mpeg", ".m4v", ".mov", ".wmv", ".ts", ".divx"}

# A complete cue-timing line and nothing else. Anchored per-line so that a timestamp
# appearing inside dialogue cannot be rewritten by accident. The trailing group keeps
# any CR and any WebVTT-style positioning that follows the second timestamp.
CUE_LINE = re.compile(
    rb"^([ \t]*)(\d+):(\d{2}):(\d{2})[,.](\d{3})([ \t]*-->[ \t]*)(\d+):(\d{2}):(\d{2})[,.](\d{3})(.*)$",
    re.MULTILINE,
)


def ms_of(h: bytes, m: bytes, s: bytes, ms: bytes) -> int:
    return (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms)


def fmt_ms(t: int) -> bytes:
    h, rem = divmod(max(t, 0), 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return b"%02d:%02d:%02d,%03d" % (h, m, s, ms)


def cue_times(data: bytes) -> list[tuple[int, int]]:
    """Every (start, end) in milliseconds. Encoding-independent: timings are ASCII."""
    return [
        (ms_of(g[1], g[2], g[3], g[4]), ms_of(g[6], g[7], g[8], g[9]))
        for g in (m.groups() for m in CUE_LINE.finditer(data))
    ]


def rescale(data: bytes, k: float) -> bytes:
    def sub(m: re.Match) -> bytes:
        g = m.groups()
        a = fmt_ms(round(ms_of(g[1], g[2], g[3], g[4]) * k))
        b = fmt_ms(round(ms_of(g[6], g[7], g[8], g[9]) * k))
        return g[0] + a + g[5] + b + g[10]

    return CUE_LINE.sub(sub, data)


def skeleton(data: bytes) -> bytes:
    """Everything that is not a timing line. Must survive a rescale byte for byte."""
    return CUE_LINE.sub(b"\x00TIMING\x00", data)


def probe_duration(ffprobe: list[str], video: pathlib.Path) -> float | None:
    cmd = ffprobe + [
        "-v", "error", "-show_entries", "format=duration",
        "-of", "json", str(video),
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=120).stdout
        return float(json.loads(out)["format"]["duration"])
    except Exception:
        return None


def siblings(video: pathlib.Path) -> list[pathlib.Path]:
    """External subtitles belonging to this video.

    Matched on the video's stem so that a folder holding two films cannot have one
    film's subtitle attributed to the other. A bare `<stem>.srt` and the language-suffixed
    `<stem>.en.srt` / `<stem>.hu.srt` forms all match; language is not filtered, because
    the ratio test below is a far better filter than a filename convention, and the
    Hungarian twin of an affected file is affected identically.
    """
    stem = video.stem.lower()
    return sorted(
        p for p in video.parent.glob("*")
        if p.suffix.lower() == ".srt" and p.stem.lower().startswith(stem)
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--path", required=True, help="file or directory to walk")
    ap.add_argument("--apply", action="store_true", help="actually rewrite (default: dry run)")
    ap.add_argument("--tolerance", type=float, default=0.25,
                    help="max %% deviation from the PAL constant to treat as this bug (default 0.25)")
    ap.add_argument("--ffprobe", default="sudo docker exec ersatztv ffprobe",
                    help="how to invoke ffprobe (default: ErsatzTV's own copy)")
    args = ap.parse_args()

    ffprobe = shlex.split(args.ffprobe)
    root = pathlib.Path(args.path)
    if not root.exists():
        print(f"no such path: {root}", file=sys.stderr)
        return 2

    videos = ([root] if root.is_file()
              else sorted(p for p in root.rglob("*") if p.suffix.lower() in VIDEO_EXT))

    print(f"{'subtitle':<52} {'video':>9} {'last cue':>9} {'ratio':>7} {'dev%':>6}  action")
    print("-" * 104)

    counts = {"fixed": 0, "would fix": 0, "wrong cut": 0, "plausible": 0,
              "already done": 0, "no duration": 0, "failed": 0}

    for video in videos:
        subs = siblings(video)
        if not subs:
            continue
        dur = probe_duration(ffprobe, video)
        if dur is None:
            for s in subs:
                counts["no duration"] += 1
                print(f"{s.name[:51]:<52} {'?':>9} {'?':>9} {'?':>7} {'?':>6}  SKIP ffprobe failed")
            continue

        for srt in subs:
            try:
                data = srt.read_bytes()
            except OSError as e:
                counts["failed"] += 1
                print(f"{srt.name[:51]:<52} {'':>9} {'':>9} {'':>7} {'':>6}  SKIP unreadable: {e}")
                continue

            cues = cue_times(data)
            if not cues:
                counts["failed"] += 1
                print(f"{srt.name[:51]:<52} {dur:>8.1f}s {'-':>9} {'-':>7} {'-':>6}  SKIP no cues found")
                continue

            last = max(e for _, e in cues) / 1000
            ratio = last / dur
            dev = abs(ratio - PAL_NTSC) / PAL_NTSC * 100

            if srt.with_suffix(".srt.orig").exists():
                counts["already done"] += 1
                verdict = "SKIP .orig exists, already rescaled"
            elif last <= dur:
                counts["plausible"] += 1
                verdict = "ok   ends inside the video"
            elif dev > args.tolerance:
                counts["wrong cut"] += 1
                verdict = "SKIP overruns, but not PAL/NTSC (needs a replacement)"
            elif not args.apply:
                counts["would fix"] += 1
                verdict = f"WOULD rescale x{SCALE:.5f} -> last cue {last * SCALE:.1f}s"
            else:
                backup = srt.with_suffix(".srt.orig")
                try:
                    shutil.copy2(srt, backup)
                    new = rescale(data, SCALE)
                    srt.write_bytes(new)

                    check = srt.read_bytes()
                    new_last = max(e for _, e in cue_times(check)) / 1000
                    if skeleton(check) != skeleton(data):
                        raise ValueError("bytes outside the timing lines changed")
                    if len(cue_times(check)) != len(cues):
                        raise ValueError("cue count changed")
                    if abs(new_last - dur) > max(5.0, dur * 0.005):
                        raise ValueError(f"last cue landed at {new_last:.1f}s, video is {dur:.1f}s")

                    counts["fixed"] += 1
                    verdict = f"FIXED last cue now {new_last:.1f}s, backup {backup.name}"
                except Exception as e:
                    if backup.exists():
                        shutil.copy2(backup, srt)
                        backup.unlink()
                    counts["failed"] += 1
                    verdict = f"FAILED {e} (original restored)"

            print(f"{srt.name[:51]:<52} {dur:>8.1f}s {last:>8.1f}s {ratio:>7.4f} {dev:>6.2f}  {verdict}")

    print("-" * 104)
    for k, v in counts.items():
        if v:
            print(f"  {k:<14} {v}")
    if not args.apply and counts["would fix"]:
        print(f"\n  dry run. Re-run with --apply to rescale those {counts['would fix']} file(s).")
    if counts["wrong cut"]:
        print(f"\n  {counts['wrong cut']} subtitle(s) overrun the video but not by the PAL/NTSC ratio.")
        print("  Those are a different cut of the programme; arithmetic cannot fix them.")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
