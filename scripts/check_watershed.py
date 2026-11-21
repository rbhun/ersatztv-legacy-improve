#!/usr/bin/env python3
"""Prove that no channel can air content above its age ceiling for the time of day.

The rule is a safety rule, so it should not rest on reading six YAML files carefully. This
walks each schedule's playout, works out the earliest time each content source can be
reached, and fails if that source's query matches anything rated above the ceiling in force
at that time.

Run from the repo root:

    python3 scripts/check_watershed.py

Exit status is 0 only if every source is clean for its slot. Read-only; touches nothing but
the audit CSV and the schedule files.

Note on method: this trusts the audit CSV, which is a snapshot. Re-run
scripts/plex_library_audit.py first if the library has changed, or the verdict is stale.

HUNGARIAN SCHEDULES. The audit CSV has no audio-language column, so `language_tag` cannot be
evaluated. It is over-approximated instead (see OVERAPPROX_FIELDS in
validate_ersatztv_queries.py): each HU query is checked as written with only its language
conjunct relaxed, which yields a superset of the real source, and a ceiling that holds for a
superset holds for every subset. Those counts are marked "upper bound"; the real ones come
from scripts/count_ersatztv_queries.py.

This replaced an earlier argument that turned out to be false. It said every HU query is its
EN counterpart plus `AND language_tag:hu*`, so a clean EN source implied a clean HU one, and the
HU sources could be left modelling as 0. Measured on 2026-11-18, 4 of the 18 language-filtered
HU sources were NOT mirrors of their EN source — so the EN check never covered them, and their
0 meant they had never been checked at all.

EXCLUSION DRIFT. A rating check cannot see a `NOT show_title:` clause, and those clauses carry
two different kinds of decision that look identical in the YAML:

  - LANGUAGE. A show has no English audio, so the EN file names it out and the HU file keeps
    it. 7th Heaven, Showder Klub, Breaking Bad and Terapia are all this kind. Divergence is
    correct.
  - AGE. A show's rating is too permissive for what it contains, so it is named out of a
    daypart by hand. Divergence would be a breach the rating check passes silently.

Nothing in the query says which kind a clause is, so every EN exclusion its HU counterpart lacks
is a failure unless the HU file declares it as a YAML comment, which ErsatzTV ignores:

    # drift-ok: NIGHT_MIX "Breaking Bad" only copies in the library are Hungarian dubs

On its first run this found six divergences, and all six were the language kind — documented
in main.yml as deliberate. It has not yet caught a real breach. It exists so that an AGE
exclusion added to an EN file cannot fail to reach the HU file without someone saying so.
"""
import glob
import os
import re
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate_ersatztv_queries import (  # noqa: E402
    JUNK,
    evaluate,
    fields,
    overapproximated,
    rows,
    tokenize,
)

PAIRS = [("main.yml", "main-hu.yml"), ("kids.yml", "kids-hu.yml"), ("movies.yml", "movies-hu.yml")]
EXCLUSION = re.compile(r'NOT show_title:"([^"]+)"')
DRIFT_OK = re.compile(r'^\s*#\s*drift-ok:\s*([A-Z_]+)\s+"([^"]+)"', re.M)

# Every content rating in the library, mapped to the age it gates on. Hungarian ratings read
# "not recommended under N", so hu/12 is age 12. US ratings are mapped to their nearest
# equivalent: PG to 10, R and TV-MA to 17, NC-17 to 18.
AGE = {
    "G": 0, "TV-G": 0, "TV-Y": 0, "hu/KN": 0, "Passed": 0, "Approved": 0,
    "hu/6": 6, "TV-Y7": 7,
    "PG": 10, "TV-PG": 10,
    "12": 12, "hu/12": 12,
    "PG-13": 13, "hu/PG-13": 13,
    "hu/14": 14, "TV-14": 14,
    "hu/16": 16, "hu/16 ": 16, "hu/16 éven aluliak számára nem ajánlott": 16,
    "R": 17, "TV-MA": 17,
    "hu/18": 18, "hu/18 ": 18, "hu/R": 18, "NC-17": 18,
    "hu/20": 20,
}

# The age ladder, as (from this minute, highest age permitted). `None` means unrestricted.
# A source is judged against the ceiling in force at the EARLIEST time it can be reached.
#
#   06:00-14:00   nothing 12+
#   14:00-18:00   nothing 16+
#   18:00-22:00   nothing 18+
#   22:00-06:00   anything
DEFAULT_POLICY = [(0, None), (6 * 60, 10), (14 * 60, 14), (18 * 60, 16), (22 * 60, None)]

# The two children's channels do not step up at all — they stay at the under-12 ceiling for
# the whole broadcast day. Nothing about the ladder forces that; it is a choice, and deleting
# these two lines puts them on the same ladder as everything else.
POLICY = {
    "kids.yml": [(0, 10)],
    "kids-hu.yml": [(0, 10)],
}


# A block may start up to this many minutes before its step: a `pad_until` that cannot fit
# another whole item leaves at most this much, and the overrun pad after it closes anything
# longer. Accepted by the user on 2026-11-19, so the ladder is enforced to this tolerance.
EARLY_START = 15


def minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def ceiling(policy, clock):
    """Highest age permitted at `clock`. Returns None for unrestricted."""
    limit = policy[0][1]
    for start, value in policy:
        if clock % (24 * 60) >= start:
            limit = value
    return limit


def source_queries(source):
    """Every query string a content source draws from.

    `search` sources carry a single `query`. `marathon` sources carry a list of `searches`,
    any of which can contribute an item, so for safety purposes a marathon is the UNION of
    its searches — exactly how the schedule treats it.
    """
    if "searches" in source:
        return list(source["searches"])
    return [source["query"]]


def shortest(queries):
    """Runtime of the shortest item any of `queries` can match, or 0 if none match."""
    toks = [tokenize(q) for q in queries]
    lengths = [
        int(r["minutes"]) for r in rows
        if r["library"] not in JUNK and (r["minutes"] or "").isdigit()
        and any(evaluate(tk, fields(r)) for tk in toks)
    ]
    return min(lengths) if lengths else 0


def earliest_starts(playout, queries):
    """The earliest clock time at which each content source can be reached.

    `pad_until` advances the clock to its own value. `count` is advanced by the SHORTEST
    runtime its source can match, which is the conservative bound: real playout can only run
    longer, so a later source can only ever be judged against a looser ceiling than this.
    That matters for the 20:00 feature film, which pushes the blocks after it towards 22:00.

    A `pad_until` that only schedules items that fit ends up to EARLY_START minutes short of
    its time. One with `stop_before_end: false` is an overrun pad: it extends the block before
    it, so its content can start anywhere from that block's start, and it only ever moves the
    clock forward, to its own time at the earliest.
    """
    clock = 0
    block_start = 0
    found = {}
    for ins in playout:
        if "wait_until" in ins:
            clock = minutes(ins["wait_until"])
            continue
        start = clock
        if "pad_until" in ins:
            end = minutes(ins["pad_until"])
            if ins.get("stop_before_end") is False:
                start = block_start
                end += clock // (24 * 60) * 24 * 60
                clock = max(clock, end)
            else:
                block_start = start
                clock = (end + 24 * 60 if ins.get("tomorrow") else end) - EARLY_START
        elif "count" in ins and ins.get("content"):
            clock += ins["count"] * shortest(queries[ins["content"]])
        for key in ("content", "fallback"):
            if ins.get(key):
                found[ins[key]] = min(found.get(ins[key], start), start)
    return found


def ratings_matched(queries):
    out = {}
    toks = [tokenize(q) for q in queries]
    for r in rows:
        if r["library"] in JUNK:
            continue
        if any(evaluate(tk, fields(r)) for tk in toks):
            out.setdefault(r["content_rating"] or "", []).append(r)
    return out


def exclusion_drift():
    """Title exclusions an EN source has that its HU counterpart lacks, minus declared ones."""
    found = []
    for en, hu in PAIRS:
        en_doc = yaml.safe_load(open(f"ersatztv/{en}", encoding="utf-8"))
        hu_text = open(f"ersatztv/{hu}", encoding="utf-8").read()
        hu_doc = yaml.safe_load(hu_text)
        en_src = {c["key"]: source_queries(c) for c in en_doc["content"]}
        declared = set(DRIFT_OK.findall(hu_text))
        for c in hu_doc["content"]:
            key = c["key"]
            if key not in en_src:
                continue
            en_ex = {t for q in en_src[key] for t in EXCLUSION.findall(q)}
            hu_ex = {t for q in source_queries(c) for t in EXCLUSION.findall(q)}
            found += [(hu, key, t) for t in sorted(en_ex - hu_ex) if (key, t) not in declared]
    return found


def main():
    failures = 0
    for path in sorted(glob.glob("ersatztv/*.yml")):
        doc = yaml.safe_load(open(path))
        if not (isinstance(doc, dict) and "playout" in doc):
            continue
        policy = POLICY.get(os.path.basename(path), DEFAULT_POLICY)
        queries = {c["key"]: source_queries(c) for c in doc["content"]}
        starts = earliest_starts(doc["playout"], queries)
        steps = " ".join(
            f"{s // 60:02d}:00->{'any' if v is None else v}" for s, v in policy
        )
        print(f"\n{path}  —  ceiling by time: {steps}")
        for key, start in sorted(starts.items(), key=lambda kv: kv[1]):
            limit = ceiling(policy, start + EARLY_START)
            by = ratings_matched(queries[key])
            total = sum(len(v) for v in by.values())
            bad, unrated = {}, {}
            for rating, items in by.items():
                age = AGE.get(rating)
                if limit is None:
                    # Unrestricted slot. An unknown rating cannot breach a ceiling that
                    # does not exist, so there is nothing to report.
                    continue
                if age is None:
                    unrated[rating or "(unrated)"] = items
                elif age > limit:
                    bad[rating] = items
            verdict = "FAIL" if bad else ("review" if unrated else "ok")
            if bad:
                failures += 1
            cap = "any" if limit is None else f"<={limit}"
            bound = "  (upper bound)" if any(overapproximated(q) for q in queries[key]) else ""
            print(f"  [{verdict:6s}] {start // 60 % 24:02d}:{start % 60:02d} cap {cap:4s} "
                  f"{key:14s} {total:5d} items{bound}")
            for k, v in sorted(bad.items(), key=lambda kv: -len(kv[1])):
                ex = ", ".join(sorted({x['show'] or x['title'] for x in v})[:3])
                print(f"            BLOCKED {k:10s} {len(v):4d}  e.g. {ex}")
            for k, v in sorted(unrated.items(), key=lambda kv: -len(kv[1])):
                ex = ", ".join(sorted({x['show'] or x['title'] for x in v})[:3])
                print(f"            unrated {k:10s} {len(v):4d}  e.g. {ex}")

    drift = exclusion_drift()
    if drift:
        print("\nexclusion drift — the EN source excludes these, its HU counterpart does not:")
        for hu, key, title in drift:
            print(f'  [DRIFT ] {hu:14s} {key:14s} "{title}"')
        print('  declare a deliberate one in the HU file:  # drift-ok: KEY "Title" <reason>')

    print()
    if failures or drift:
        if failures:
            print(f"RESULT: {failures} source(s) admit content above the ceiling for their slot")
        if drift:
            print(f"RESULT: {len(drift)} title exclusion(s) missing from a Hungarian schedule")
        return 1
    print("RESULT: every content source is within the age ceiling for its earliest slot,")
    print("        and every Hungarian schedule carries its English counterpart's exclusions")
    print("        or declares why it does not")
    return 0


if __name__ == "__main__":
    sys.exit(main())
