#!/usr/bin/env python3
"""Audit the Plex library's metadata so ErsatzTV channel queries can be written from
evidence instead of guesswork. Writes a readable report and a full CSV inventory.

WHY THIS EXISTS
    The schedules in ersatztv/*.yml select content with genre queries. Anything in Plex
    that carries no genre matches no genre query, so it silently never airs. Likewise,
    `content_rating` values are region-specific, so guessing "TV-Y" or "PG" for a European
    library produces empty dayparts. This reports what the library actually contains.

    Genres live on the MOVIE and on the SHOW, never on the episode. So a show with no
    genre takes all of its episodes down with it -- the report calls that out explicitly,
    because one missing label on a 200-episode show is a much bigger hole than one movie.

USAGE
    Save a Plex token to ~/.plex_token (chmod 600), then:

        python3 scripts/plex_library_audit.py

    Get a token from Plex Web: open any item, then ... -> Get Info -> View XML. The
    browser URL contains X-Plex-Token=<token>.

    The token is read from the file inside this script, so it never appears in a command
    line or in agent context -- the same pattern ha_diag uses for the HA token.

OPTIONS
    --out-dir DIR     where to write results (default: ersatztv/audit)
    --no-episodes     shows only; skip the per-episode rows in the CSV
    --url URL         Plex base URL (default: http://plex.internal:32400)
    --token-file F    token location (default: ~/.plex_token)

OUTPUT
    <out-dir>/library-audit.txt      the report, as printed
    <out-dir>/library-inventory.csv  one row per movie, show and episode, with labels

READ-ONLY
    Issues HTTP GET requests only. Never writes to Plex.
"""

import argparse
import collections
import csv
import datetime
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

TIMEOUT = 30

# Libraries Plex types as "movie" that are not programming: home video and demo loops.
# Every channel query must exclude these, so their missing metadata is not a defect.
JUNK_LIBRARIES = {"Demos", "Other videos"}

# Titles that never matched a metadata agent and kept their release name. Word boundaries
# matter: without \b on PROPER, this matches the "Proper" inside "The Property Division".
RELEASE_NAME = re.compile(
    r"(\bWEB[ ._-]?DL\b|\bWEBRip\b|\bBluRay\b|\bBDRip\b|\bHDTV\b|\bx26[45]\b"
    r"|\bH\.?26[45]\b|\bDD5\b|\bDDP\b|\bAAC\b|\bXviD\b|\b1080p\b|\b720p\b|\b2160p\b"
    r"|\bREMUX\b|\bPROPER\b|\bSample\b|\bFULCRUM\b|\bDSNP\b|\bRARBG\b|\bS0\d\b)",
    re.IGNORECASE,
)

# Mirrors the genre sets used by the dayparts in ersatztv/*.yml, so the audit reports how
# much content each daypart would actually find.
DAYPARTS = {
    "main.yml MORNING_KIDS": ("episode", {"animation", "family", "children"}),
    "main.yml DAYTIME_SHOWS": ("episode", {"comedy", "sitcom"}),
    "main.yml EARLY_EVENING": ("episode", {"drama", "crime", "adventure"}),
    "main.yml PRIME_MOVIE": ("movie", None),          # everything except animation/horror
    "main.yml LATE_NIGHT": ("movie", {"horror", "thriller", "mystery"}),
    "kids.yml PRESCHOOL": ("episode", {"animation", "family", "children"}),
    "kids.yml CARTOONS": ("episode", {"animation"}),
    "kids.yml AFTER_SCHOOL": ("episode", {"animation", "family", "adventure"}),
    "kids.yml KIDS_MOVIES": ("movie", {"animation", "family"}),
    "movies.yml MATINEE": ("movie", {"family", "adventure", "animation"}),
    "movies.yml ACTION": ("movie", {"action", "adventure"}),
    "movies.yml COMEDY": ("movie", {"comedy"}),
    "movies.yml PRIME_DRAMA": ("movie", {"drama", "thriller", "crime"}),
    "movies.yml LATE_GENRE": ("movie", {"horror", "mystery"}),
}
# For the PRIME_MOVIE bucket, which is an exclusion rather than an inclusion.
PRIME_MOVIE_EXCLUDE = {"animation", "horror"}


class Report:
    """Accumulates lines so the same text goes to stdout and to the report file."""

    def __init__(self):
        self.lines = []

    def __call__(self, line=""):
        print(line)
        self.lines.append(line)

    def save(self, path):
        path.write_text("\n".join(self.lines) + "\n")


def read_token(token_file):
    env = os.environ.get("PLEX_TOKEN")
    if env:
        return env.strip()
    if not token_file.exists():
        sys.exit(
            "No Plex token found.\n"
            "  Save one to %s (chmod 600), or set PLEX_TOKEN.\n"
            "  Plex Web -> any item -> ... -> Get Info -> View XML; the URL contains "
            "X-Plex-Token." % token_file
        )
    token = token_file.read_text().strip()
    if not token:
        sys.exit("%s is empty." % token_file)
    return token


def get(base, path, token, **params):
    params["X-Plex-Token"] = token
    url = "%s%s?%s" % (base, path, urllib.parse.urlencode(params))
    req = urllib.request.Request(url, headers={"Accept": "application/xml"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return ET.fromstring(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            sys.exit("Plex rejected the token (401). Generate a fresh one.")
        sys.exit("HTTP %s fetching %s" % (exc.code, path))
    except urllib.error.URLError as exc:
        sys.exit("Could not reach Plex at %s (%s)" % (base, exc.reason))


def genres_of(elem):
    return sorted({g.get("tag", "").strip().lower()
                   for g in elem.findall("Genre") if g.get("tag")})


def file_of(elem):
    """Basename of the backing file. Full paths are deliberately not recorded."""
    part = elem.find(".//Part")
    if part is None:
        return ""
    return (part.get("file") or "").rsplit("/", 1)[-1]


def size_mib_of(elem):
    part = elem.find(".//Part")
    try:
        return int(part.get("size")) / (1024 * 1024)
    except (AttributeError, TypeError, ValueError):
        return 0.0


def ratings_of(elem):
    """Critic, audience and personal scores.

    ErsatzTV's search index has NO rating field of any kind -- see its search reference --
    so these cannot be queried directly in a schedule. They are collected because they are
    usable indirectly: build a smart collection in Plex filtered on rating, and ErsatzTV can
    then match it with `collection:"Name"`, which IS a searchable field.
    """
    return {
        "critic_rating": elem.get("rating") or "",
        "audience_rating": elem.get("audienceRating") or "",
        "user_rating": elem.get("userRating") or "",
    }


def minutes_of(elem):
    raw = elem.get("duration")
    if not raw:
        return ""          # shows carry no duration; blank beats a misleading 0
    try:
        return round(int(raw) / 60000)
    except (TypeError, ValueError):
        return ""


def plural(n, singular, suffix="s"):
    return "%d %s%s" % (n, singular, "" if n == 1 else suffix)


def fill_missing_genres(base, token, items, log):
    """Plex sometimes omits Genre children from section listings. Detail-fetch only the
    items that came back bare, in batches, so a rich listing costs nothing."""
    bare = [i.get("ratingKey") for i in items if not genres_of(i) and i.get("ratingKey")]
    detail = {}
    if not bare:
        return detail
    print("  (fetching genre detail for %d items...)" % len(bare), file=sys.stderr)
    for start in range(0, len(bare), 50):
        chunk = bare[start:start + 50]
        try:
            meta = get(base, "/library/metadata/%s" % ",".join(chunk), token)
        except SystemExit:
            continue
        for elem in list(meta):
            rk = elem.get("ratingKey")
            if rk:
                detail[rk] = genres_of(elem)
    return detail


def histogram(out, title, counter, total, note=""):
    distinct = len([k for k in counter if k != "(none)"])
    out("  %s (%d distinct)%s:" % (title, distinct, note))
    # Descending by count, but "(none)" always last: it is a gap, not a category, and
    # tie-ordering would otherwise bury it mid-list where it reads like just another label.
    ordered = sorted(counter.items(),
                     key=lambda kv: (kv[0] == "(none)", -kv[1], kv[0]))
    for name, count in ordered:
        pct = (count / total * 100) if total else 0
        flag = "   <-- matches no query" if name == "(none)" else ""
        out("     %-30s %6d  %5.1f%%%s" % (name, count, pct, flag))


def main():
    ap = argparse.ArgumentParser(description="Audit Plex metadata for ErsatzTV queries.")
    ap.add_argument("--out-dir", default="ersatztv/audit")
    ap.add_argument("--no-episodes", action="store_true")
    ap.add_argument("--url", default=os.environ.get("PLEX_URL",
                                                    "http://plex.internal:32400"))
    ap.add_argument("--token-file", default=os.environ.get("PLEX_TOKEN_FILE",
                                                           "~/.plex_token"))
    args = ap.parse_args()

    base = args.url.rstrip("/")
    token = read_token(pathlib.Path(args.token_file).expanduser())
    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    out = Report()
    out("Plex library audit (read-only)")
    out("  server:    %s" % base)
    out("  generated: %s" % datetime.datetime.now().isoformat(timespec="seconds"))

    rows = []            # CSV inventory
    movie_genre_sets = []
    show_genre_sets = []
    episode_genre_sets = []
    genreless_shows = []  # (title, episode_count)

    sections = get(base, "/library/sections", token)
    found = False

    for section in sections.findall("Directory"):
        stype = section.get("type")
        if stype not in ("movie", "show"):
            continue
        found = True
        key, lib = section.get("key"), section.get("title")

        listing = get(base, "/library/sections/%s/all" % key, token)
        items = listing.findall("Video") + listing.findall("Directory")
        if not items:
            out("\n=== %s [%s] === empty or unreadable" % (lib, stype))
            continue

        detail = fill_missing_genres(base, token, items, out)

        genre_counter = collections.Counter()
        rating_counter = collections.Counter()
        no_genre = []
        show_genres = {}   # ratingKey -> genres, for joining onto episodes

        for item in items:
            rk = item.get("ratingKey")
            title = item.get("title") or "(untitled)"
            year = item.get("year") or ""
            gs = genres_of(item) or detail.get(rk, [])
            rating = item.get("contentRating") or ""

            if stype == "movie":
                movie_genre_sets.append(set(gs))
            else:
                show_genres[rk] = gs
                show_genre_sets.append(set(gs))

            for g in (gs or ["(none)"]):
                genre_counter[g] += 1
            rating_counter[rating or "(none)"] += 1
            if not gs:
                no_genre.append((title, year, rk))

            rows.append({
                "library": lib,
                "kind": stype,
                "title": title,
                "show": "",
                "season": "",
                "episode": "",
                "year": year,
                "genres": "|".join(gs),
                "content_rating": rating,
                "minutes": minutes_of(item),
                "rating_key": rk,
                "has_genre": "yes" if gs else "NO",
                "file": file_of(item),
                "size_mib": "%.0f" % size_mib_of(item) if size_mib_of(item) else "",
                **ratings_of(item),
            })

        total = len(items)
        out("\n=== %s  [%s, %d items] ===" % (lib, stype, total))
        histogram(out, "genres", genre_counter, total,
                  note=" -- items carry several, so percentages exceed 100%")
        histogram(out, "content ratings", rating_counter, total)

        # Episodes: one request for the whole section. Genres are inherited from the show.
        ep_counts = collections.Counter()
        if stype == "show" and not args.no_episodes:
            eps = get(base, "/library/sections/%s/all" % key, token, type="4")
            ep_items = eps.findall("Video")
            out("  episodes: %d" % len(ep_items))
            for ep in ep_items:
                show_rk = ep.get("grandparentRatingKey")
                gs = show_genres.get(show_rk, [])
                ep_counts[show_rk] += 1
                episode_genre_sets.append(set(gs))
                rows.append({
                    "library": lib,
                    "kind": "episode",
                    "title": ep.get("title") or "(untitled)",
                    "show": ep.get("grandparentTitle") or "",
                    "season": ep.get("parentIndex") or "",
                    "episode": ep.get("index") or "",
                    "year": ep.get("year") or "",
                    "genres": "|".join(gs),
                    "content_rating": ep.get("contentRating") or "",
                    "minutes": minutes_of(ep),
                    "rating_key": ep.get("ratingKey"),
                    "has_genre": "yes" if gs else "NO",
                    "file": file_of(ep),
                    "size_mib": "%.0f" % size_mib_of(ep) if size_mib_of(ep) else "",
                    **ratings_of(ep),
                })

        if no_genre:
            out("  %s with NO genre -- cannot be scheduled by any genre query:"
                % plural(len(no_genre), "show" if stype == "show" else "movie"))
            for title, year, rk in sorted(no_genre)[:40]:
                extra = ""
                if stype == "show":
                    n = ep_counts.get(rk, 0)
                    extra = "  [%s blocked]" % plural(n, "episode") if n else ""
                    genreless_shows.append((title, n))
                out("     - %s %s%s" % (title, "(%s)" % year if year else "", extra))
            if len(no_genre) > 40:
                out("     ... and %d more" % (len(no_genre) - 40))

    if not found:
        sys.exit("\nNo movie or show libraries found.")

    # ── Daypart coverage ─────────────────────────────────────────────────────────
    out("\n\n=== DAYPART COVERAGE (genre sets used by ersatztv/*.yml) ===")
    out("Episode counts use the parent show's genres, which is how ErsatzTV indexes them.")
    out("")
    for label, (kind, wanted) in DAYPARTS.items():
        pool = movie_genre_sets if kind == "movie" else episode_genre_sets
        if wanted is None:
            hits = sum(1 for gs in pool if gs and not (gs & PRIME_MOVIE_EXCLUDE))
        else:
            hits = sum(1 for gs in pool if gs & wanted)
        if not pool:
            verdict = "  <-- NO LIBRARY OF THIS TYPE"
        elif hits == 0:
            verdict = "  <-- EMPTY: this daypart would be dead air"
        elif hits < 5:
            verdict = "  <-- very thin, will repeat heavily"
        else:
            verdict = ""
        out("  %-28s %-9s %6d of %-6d%s" % (label, "(%s)" % kind, hits, len(pool), verdict))

    if genreless_shows:
        blocked = sum(n for _, n in genreless_shows)
        out("")
        out("  %d episode%s unreachable because the parent show carries no genre."
            % (blocked, " is" if blocked == 1 else "s are"))
        out("  Fixing metadata on those shows in Plex is the highest-leverage change.")

    # ── Metadata gaps ────────────────────────────────────────────────────────────
    # Counted over SCHEDULABLE titles only. Libraries listed in JUNK_LIBRARIES are home
    # video and demo loops: they are meant to be excluded from every channel, so their
    # missing metadata is not a defect and counting it would drown out the real gaps.
    out("\n\n=== METADATA GAPS (schedulable titles only) ===")
    out("Junk libraries excluded: %s" % ", ".join(sorted(JUNK_LIBRARIES)))
    out("Genres live on movies and shows, never on episodes, so those are the units that")
    out("matter. An unlabelled show takes all of its episodes down with it.")
    out("")

    for kind in ("movie", "show"):
        units = [r for r in rows if r["kind"] == kind
                 and r["library"] not in JUNK_LIBRARIES]
        excluded = sum(1 for r in rows if r["kind"] == kind
                       and r["library"] in JUNK_LIBRARIES)
        if not units:
            continue
        out("  %sS -- %d schedulable (%d more in junk libraries, ignored)"
            % (kind.upper(), len(units), excluded))
        for field, label in (("genres", "no genre"),
                             ("content_rating", "no content rating"),
                             ("year", "no year")):
            missing = [r for r in units if not r[field]]
            out("    %-22s %4d / %-4d  %5.1f%%"
                % (label, len(missing), len(units),
                   len(missing) / len(units) * 100))
        raw = [r for r in units if RELEASE_NAME.search(r["title"])]
        out("    %-22s %4d / %-4d" % ("raw release name", len(raw), len(units)))
        for r in raw:
            out("        - [%s] %s" % (r["library"], r["title"][:66]))
        out("")

    eps = [r for r in rows if r["kind"] == "episode"]
    if eps:
        out("  EPISODES -- %d total" % len(eps))
        out("    %-22s %4d   (parent show unlabelled)"
            % ("no genre", sum(1 for r in eps if not r["genres"])))
        out("    %-22s %4d" % ("no duration",
                               sum(1 for r in eps if not r["minutes"])))

    # ── Which exact titles are missing which exact fields ────────────────────────
    out("\n\n=== MISSING FIELDS, BY TITLE ===")
    out("Only schedulable libraries. `genre` is the one that actually breaks scheduling;")
    out("a missing content rating or year costs nothing unless you query on it.")
    gap_fields = [("genres", "genre"), ("content_rating", "cert"),
                  ("year", "year"), ("audience_rating", "audience")]
    for kind in ("movie", "show"):
        items = [r for r in rows
                 if r["kind"] == kind and r["library"] not in JUNK_LIBRARIES]
        gapped = []
        for r in items:
            g = [lbl for f, lbl in gap_fields if not str(r.get(f) or "").strip()]
            if g:
                gapped.append((len(g), r, g))
        gapped.sort(key=lambda x: (-x[0], x[1]["library"], x[1]["title"]))
        out("\n  %sS -- %d of %d have at least one gap"
            % (kind.upper(), len(gapped), len(items)))
        for _, r, g in gapped:
            out("    [%-9s] %-46s missing: %s"
                % (r["library"], r["title"][:46], ", ".join(g)))
    out("\n  Note: critic ratings are absent on every show. That is normal -- Plex does")
    out("  not carry critic scores for TV, so it is not a gap you can fix.")

    # ── The gap that matters most is a missing *file*, not missing metadata ───────
    out("\n\n=== RUNTIME SANITY (sample files masquerading as features) ===")
    out("A sample clip still carries the real film's title, poster and ratings, so it looks")
    out("perfectly healthy in Plex -- and ErsatzTV will happily drop it into a two-hour")
    out("prime slot, where it ends after 70 seconds. Duration is the only tell.")
    short = []
    for r in rows:
        if r["kind"] != "movie" or r["library"] in JUNK_LIBRARIES:
            continue
        mins = str(r.get("minutes") or "")
        if mins.isdigit() and int(mins) < 60:
            short.append((int(mins), r))
    short.sort(key=lambda x: (x[0], x[1]["title"]))
    out("\n  %d schedulable films run under 60 minutes:" % len(short))
    for mins, r in short:
        fn = str(r.get("file") or "")
        verdict = "SAMPLE" if "sample" in fn.lower() else "check"
        out("    %3d min  %-6s  %-40s %s"
            % (mins, verdict, r["title"][:40], fn[:44]))
    out("\n  The schedules guard against these with `minutes:[60 TO 400]` on every film")
    out("  source, so nothing here can reach air. Still worth replacing the files.")

    # duplicate titles, and two entries sharing one file
    out("\n  Duplicates:")
    by_title = collections.defaultdict(set)
    by_file = collections.defaultdict(set)
    for r in rows:
        if r["kind"] == "movie" and r["library"] not in JUNK_LIBRARIES:
            by_title[r["title"]].add(r["library"])
            # Keyed on name *and* size: disc rips all share basenames like 00000.m2ts
            # without being the same file, and only full paths would disambiguate them,
            # which this audit deliberately does not record.
            if r.get("file"):
                by_file[(r["file"], r.get("size_mib"))].add(r["title"])
    for title, libs in sorted(by_title.items()):
        if len(libs) > 1:
            out("    same title in %s: %s" % (sorted(libs), title[:52]))
    for (fn, size), titles in sorted(by_file.items()):
        if len(titles) > 1:
            out("    one file (%s MiB), %d entries: %s -> %s"
                % (size or "?", len(titles), fn[:30], ", ".join(sorted(titles))[:44]))

    # ── Ratings ──────────────────────────────────────────────────────────────────
    # ErsatzTV cannot query these. Reported so a Plex smart collection can be built on a
    # sensible threshold, which ErsatzTV CAN then match via `collection:"Name"`.
    out("\n\n=== RATINGS (not queryable in ErsatzTV -- use a Plex collection) ===")
    films = [r for r in rows if r["kind"] == "movie"
             and r["library"] not in JUNK_LIBRARIES]
    for field, label in (("critic_rating", "critic"),
                         ("audience_rating", "audience"),
                         ("user_rating", "your own")):
        vals = []
        for r in films:
            try:
                vals.append(float(r[field]))
            except (TypeError, ValueError):
                pass
        if not vals:
            out("  %-10s no data on any film" % label)
            continue
        vals.sort()
        out("  %-10s %d of %d films (%.0f%%)  median %.1f  range %.1f-%.1f"
            % (label, len(vals), len(films), len(vals) / len(films) * 100,
               vals[len(vals) // 2], vals[0], vals[-1]))
        for lo in (9, 8, 7, 6):
            out("       >= %-4s %4d films" % (lo, sum(1 for v in vals if v >= lo)))

    # ── Write files ──────────────────────────────────────────────────────────────
    report_path = out_dir / "library-audit.txt"
    csv_path = out_dir / "library-inventory.csv"

    out("")
    out("Wrote %s" % report_path)
    out("Wrote %s  (%d rows)" % (csv_path, len(rows)))
    report_path.write_text("\n".join(out.lines) + "\n")

    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "library", "kind", "title", "show", "season", "episode", "year",
            "genres", "content_rating", "minutes", "rating_key", "has_genre",
            "critic_rating", "audience_rating", "user_rating", "file", "size_mib",
        ])
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
