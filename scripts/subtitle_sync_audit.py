#!/usr/bin/env python3
"""Find external subtitle files whose timings cannot match the video they sit next to.

WHY THIS EXISTS
    ErsatzTV burns subtitles into the picture, so a mistimed subtitle file is not
    something a viewer can switch off from the sofa -- it ruins the programme. Reported
    symptom was "all the files have their subtitles off-sync", which sounded like an
    ErsatzTV bug. It is substantially not: a quarter of the external English subtitles
    in this library provably belong to a different cut of the video.

HOW IT DETECTS A MISMATCH
    Plex serves subtitle streams over HTTP, so each file can be read and its final cue
    compared against the video's real runtime.

    A subtitle whose last cue falls AFTER the end of the video cannot possibly be
    correct. That is the whole test, and it is conservative on purpose: it produces no
    false positives, because there is no legitimate reason for dialogue to be timed past
    the closing frame.

    A stretch factor near 1.0427 is the signature of a PAL/NTSC mismatch -- 25 fps
    against 23.976 fps. Those are mechanically repairable by rescaling every timestamp by
    23.976/25. Anything stretched further than that is a different cut of the programme
    and needs a replacement subtitle, not arithmetic.

KNOWN BLIND SPOT, AND IT IS A BIG ONE
    This can only see subtitles that run too LONG. A subtitle file with a constant offset
    (consistently three seconds early), or one that is too short, passes as "plausible"
    and is indistinguishable from a good one without listening to the audio. **So the
    figure this reports is a floor, not an estimate.** A clean result here does not mean
    the subtitles are correct; it means this particular test found nothing.

    Embedded subtitles are also skipped entirely -- they cannot be fetched over HTTP and
    are far more likely to be correct, having shipped inside the file.

USAGE
    Save a Plex token to ~/.plex_token (chmod 600), then:

        python3 scripts/subtitle_sync_audit.py --lang en
        python3 scripts/subtitle_sync_audit.py --lang hu --sample 200

OPTIONS
    --lang CODE       subtitle language prefix to audit (default: en)
    --sample N        audit a random N items instead of everything; 0 = all (default: 0)
    --min-minutes N   ignore items shorter than this (default: 15)
    --out-dir DIR     where to write the report (default: ersatztv/audit)
    --url URL         Plex base URL
    --token-file F    token location (default: ~/.plex_token)
    --inventory F     the CSV from plex_library_audit.py, used to pick candidates

OUTPUT
    <out-dir>/subtitle-sync-<lang>.txt   the report, as printed
    <out-dir>/subtitle-sync-<lang>.csv   one row per mismatch, with a scale factor

READ-ONLY
    Issues HTTP GET requests only. Never writes to Plex and never touches media files.
    The CSV it writes is a worklist for a human, not something applied automatically.
"""

import argparse
import collections
import csv
import json
import pathlib
import random
import re
import sys
import urllib.error
import urllib.request

TIMEOUT = 30

# 25 fps against 23.976 fps. A subtitle timed for one and played against the other
# drifts by this factor, which is why the error grows through the episode rather than
# sitting still -- about 54 seconds by the end of a 21-minute sitcom.
PAL_NTSC = 25.0 / 23.976
PAL_BAND = (1.015, 1.065)

# A subtitle may legitimately end a little before the video (closing credits carry no
# dialogue). It may never end after it. The small allowance absorbs rounding in Plex's
# reported duration.
TOLERANCE = 1.004

CUE = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lang", default="en")
    p.add_argument("--sample", type=int, default=0)
    p.add_argument("--min-minutes", type=int, default=15)
    p.add_argument("--out-dir", default="ersatztv/audit")
    p.add_argument("--url", default="http://plex.internal:32400")
    p.add_argument("--token-file", default=str(pathlib.Path.home() / ".plex_token"))
    p.add_argument("--inventory", default="ersatztv/audit/library-inventory.csv")
    return p.parse_args()


def read_token(path: str) -> str:
    try:
        return pathlib.Path(path).read_text().strip()
    except OSError as exc:
        sys.exit(f"cannot read Plex token from {path}: {exc}")


class Plex:
    def __init__(self, base: str, token: str) -> None:
        self.base = base.rstrip("/")
        self.token = token

    def _open(self, path: str, accept: str):
        req = urllib.request.Request(self.base + path,
                                    headers={"X-Plex-Token": self.token, "Accept": accept})
        return urllib.request.urlopen(req, timeout=TIMEOUT)

    def json(self, path: str):
        return json.load(self._open(path, "application/json"))

    def text(self, path: str) -> str:
        return self._open(path, "*/*").read().decode("utf-8", "replace")


def last_cue_ms(body: str) -> int:
    """The timestamp of the final cue, in milliseconds. 0 when nothing parses."""
    stamps = [int(h) * 3600000 + int(m) * 60000 + int(s) * 1000 + int(ms)
              for h, m, s, ms in CUE.findall(body)]
    return max(stamps) if stamps else 0


def candidates(inventory: str, min_minutes: int) -> list[dict]:
    try:
        rows = list(csv.DictReader(open(inventory, encoding="utf-8")))
    except OSError as exc:
        sys.exit(f"cannot read {inventory}: {exc}\nrun scripts/plex_library_audit.py first")
    return [r for r in rows
            if r["kind"] in ("episode", "movie")
            and r["minutes"] and int(r["minutes"]) >= min_minutes]


def audit(plex: Plex, items: list[dict], lang: str):
    findings, checked, skipped = [], 0, 0
    for row in items:
        try:
            meta = plex.json(f"/library/metadata/{row['rating_key']}")
            entry = meta["MediaContainer"]["Metadata"][0]
        except (urllib.error.URLError, KeyError, IndexError, ValueError):
            skipped += 1
            continue

        duration = entry.get("duration") or 0
        if not duration:
            skipped += 1
            continue

        # Only the first version. ErsatzTV picks one too, and we cannot see which.
        streams = []
        for media in entry.get("Media", [])[:1]:
            for part in media.get("Part", [])[:1]:
                streams += [s for s in part.get("Stream", [])
                            if s.get("streamType") == 3 and s.get("key")
                            and (s.get("languageTag") or "").lower().startswith(lang)]
        if not streams:
            continue

        try:
            cue = last_cue_ms(plex.text(streams[0]["key"]))
        except (urllib.error.URLError, ValueError):
            skipped += 1
            continue
        if cue < 60000:          # a forced/signs-only track, nothing to compare
            continue

        checked += 1
        ratio = cue / duration
        if ratio <= TOLERANCE:
            continue

        findings.append({
            "show": entry.get("grandparentTitle") or "",
            "title": entry.get("title") or "",
            "library": row["library"],
            "rating_key": row["rating_key"],
            "video_minutes": round(duration / 60000, 1),
            "last_cue_minutes": round(cue / 60000, 1),
            "ratio": round(ratio, 4),
            "pal_ntsc": PAL_BAND[0] < ratio < PAL_BAND[1],
            "suggested_scale": round(1 / PAL_NTSC, 5) if PAL_BAND[0] < ratio < PAL_BAND[1] else "",
            "file": row["file"],
        })
    return findings, checked, skipped


def report(findings: list[dict], checked: int, skipped: int, lang: str) -> str:
    out = []
    w = out.append
    w(f"EXTERNAL '{lang}' SUBTITLE TIMING AUDIT")
    w("=" * 72)
    w("")
    if not checked:
        w("No items had an external subtitle in this language. Nothing to check.")
        return "\n".join(out)

    bad = len(findings)
    w(f"items with an external {lang!r} subtitle   {checked}")
    w(f"subtitle ends past the end of video     {bad}  ({bad / checked:.0%})")
    w(f"  of those, a PAL/NTSC stretch             {sum(1 for f in findings if f['pal_ntsc'])}")
    w(f"items skipped (no duration or fetch error) {skipped}")
    w("")
    w("This counts only subtitles that run too LONG, which is the one failure mode that")
    w("can be proven without listening. A constant offset passes this test, so treat the")
    w("number above as a floor.")
    w("")

    if not findings:
        return "\n".join(out)

    w("BY SHOW")
    w("-" * 72)
    by_show = collections.Counter(f["show"] or "(films)" for f in findings)
    for show, n in by_show.most_common():
        w(f"  {n:4}  {show}")
    w("")

    w("WORST OFFENDERS")
    w("-" * 72)
    for f in sorted(findings, key=lambda x: -x["ratio"])[:20]:
        tag = "PAL/NTSC" if f["pal_ntsc"] else "wrong cut"
        w(f"  ratio {f['ratio']:.3f}  video {f['video_minutes']:6.1f}m  "
          f"subtitle ends {f['last_cue_minutes']:6.1f}m  [{tag}]")
        w(f"      {f['show']} — {f['title']}")
    w("")

    w("WHAT TO DO")
    w("-" * 72)
    w("  PAL/NTSC rows are mechanically repairable: multiply every timestamp in the")
    w(f"  subtitle by {1 / PAL_NTSC:.5f}. The `suggested_scale` column carries that factor.")
    w("  Everything else is a different cut of the programme and needs a replacement")
    w("  subtitle; rescaling will not help.")
    w("")
    w("  The alternative, if this is not worth repairing title by title, is to stop")
    w("  burning same-language subtitles over audio the viewer already understands —")
    w("  see the English items at the top of ersatztv/stream-selector-en.yml.")
    return "\n".join(out)


def main() -> int:
    args = parse_args()
    plex = Plex(args.url, read_token(args.token_file))

    items = candidates(args.inventory, args.min_minutes)
    if args.sample and args.sample < len(items):
        random.seed(42)
        items = random.sample(items, args.sample)

    findings, checked, skipped = audit(plex, items, args.lang)
    text = report(findings, checked, skipped, args.lang)
    print(text)

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"subtitle-sync-{args.lang}.txt").write_text(text + "\n", encoding="utf-8")

    csv_path = out_dir / f"subtitle-sync-{args.lang}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        cols = ["library", "show", "title", "video_minutes", "last_cue_minutes", "ratio",
                "pal_ntsc", "suggested_scale", "rating_key", "file"]
        writer = csv.DictWriter(fh, fieldnames=cols)
        writer.writeheader()
        for f in sorted(findings, key=lambda x: (x["show"], x["title"])):
            writer.writerow({c: f[c] for c in cols})

    print(f"\nwrote {out_dir}/subtitle-sync-{args.lang}.txt and .csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
