#!/usr/bin/env python3
# Count every content source in the sequential schedules against the LIVE ErsatzTV index.
#
#     python3 scripts/count_ersatztv_queries.py --url http://host:8409
#
# WHY THIS EXISTS ALONGSIDE validate_ersatztv_queries.py
#     That script reimplements ErsatzTV's query language in Python and evaluates it against a
#     CSV exported from Plex. It is fast, works offline, and models ErsatzTV's per-type field
#     list — which is how it catches the `genre` vs `show_genre` mistake. But it is a model,
#     and a model cannot tell you how ErsatzTV's Lucene index actually tokenises a value.
#     That blind spot is not hypothetical: a source expected to match 25 films returned 12,
#     and the leading suspicion was that `content_rating:"hu/KN"` matches nothing because
#     Lucene splits on the forward slash. No amount of local modelling can answer that.
#
#     This script asks ErsatzTV instead. It reads the count ErsatzTV itself reports, so the
#     answer is ground truth by construction. Use both: the model explains *why* a count is
#     what it is, this one establishes *what* the count really is.
#
# READ-ONLY by design. It issues GETs to the search page and parses the rendered count. It
# never adds to a collection, never saves a search, never touches a playout.
#
# The count is read out of the server-rendered HTML rather than the API, because ErsatzTV's
# API requires a key (/api/version returns 401 since 26.8.1) while the UI does not.

import argparse
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

import yaml

SCHEDULES = [
    "main.yml",
    "main-hu.yml",
    "kids.yml",
    "kids-hu.yml",
    "movies.yml",
    "movies-hu.yml",
]

# ErsatzTV renders one heading per media type the query matched, each with its own count.
# A query can match several types at once, so every marker is collected and summed.
COUNT = re.compile(
    r">\s*([0-9,]+)\s+(Movies|Shows|Seasons|Episodes|Artists|Music Videos|Songs|Other Videos|Images|Remote Streams)\s*<"
)


def search_count(base, query, timeout):
    """Ask ErsatzTV how many items a query matches. Returns (total, breakdown)."""
    url = base.rstrip("/") + "/search?query=" + urllib.parse.quote(query, safe="")
    req = urllib.request.Request(url, headers={"Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        html = r.read().decode("utf-8", "replace")
    found = [(int(n.replace(",", "")), kind) for n, kind in COUNT.findall(html)]
    # Deduplicate: the same heading can appear in both the summary bar and the section
    # header, which would otherwise double every count.
    seen = {}
    for n, kind in found:
        seen[kind] = max(seen.get(kind, 0), n)
    return sum(seen.values()), seen


def sources(path):
    """Yield (key, [queries]) for every content source in a schedule file."""
    doc = yaml.safe_load(open(path, encoding="utf-8"))
    for c in doc.get("content", []) or []:
        key = c.get("key", "<unnamed>")
        if "searches" in c:
            # A marathon's source is the UNION of its searches, so the per-search counts
            # below are reported individually; their sum is an upper bound on the union.
            yield key, list(c["searches"]), True
        elif "query" in c:
            yield key, [c["query"]], False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="e.g. http://host:8409")
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--dir", default="ersatztv")
    ap.add_argument(
        "--query",
        action="append",
        default=[],
        help="count an ad-hoc query instead of reading the schedules; repeatable",
    )
    args = ap.parse_args()

    if args.query:
        for q in args.query:
            try:
                total, breakdown = search_count(args.url, q, args.timeout)
            except (urllib.error.URLError, OSError) as e:
                print(f"  ERROR  {q}\n         {e}", file=sys.stderr)
                continue
            detail = ", ".join(f"{n} {k}" for k, n in sorted(breakdown.items()))
            print(f"{total:>7}  {detail or '-':<28}  {q}")
        return 0

    empty = []
    for name in SCHEDULES:
        path = f"{args.dir}/{name}"
        print(f"\n=== {name}")
        for key, queries, is_union in sources(path):
            for i, q in enumerate(queries):
                label = f"{key}[{i}]" if is_union else key
                try:
                    total, breakdown = search_count(args.url, q, args.timeout)
                except (urllib.error.URLError, OSError) as e:
                    print(f"  ERROR    {label:<22} {e}", file=sys.stderr)
                    continue
                detail = ", ".join(f"{n} {k}" for k, n in sorted(breakdown.items()))
                flag = "  <-- EMPTY, this is dead air" if total == 0 else ""
                print(f"  {total:>6}  {label:<22} {detail or '-'}{flag}")
                if total == 0:
                    empty.append(f"{name}:{label}")

    print()
    if empty:
        print(f"{len(empty)} EMPTY SOURCE(S) — each one is dead air ErsatzTV will not warn about:")
        for e in empty:
            print(f"  {e}")
        return 1
    print("every content source matches at least one item")
    return 0


if __name__ == "__main__":
    sys.exit(main())
