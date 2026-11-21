#!/usr/bin/env python3
# Validate the ErsatzTV sequential schedules against the real Plex library.
#
# Run scripts/plex_library_audit.py first; this reads the CSV it writes.
#
#     python3 scripts/plex_library_audit.py
#     python3 scripts/validate_ersatztv_queries.py
#
# Checks two things that fail silently inside ErsatzTV:
#
#   1. Every content source matches at least one item. An empty source is dead air and
#      ErsatzTV issues no warning for it.
#   2. Every `content:` reference in the playout resolves to a declared key.
#
# It implements only the query subset these schedules use: AND/OR/NOT, parentheses,
# field:value, field:"quoted value", and field:[lo TO hi] ranges. It deliberately models
# ErsatzTV's per-type field list, so an episode exposes `show_genre` and
# `show_content_rating` but NOT `genre` -- which is the mistake it exists to catch.
#
# Two parser bugs were found while writing this, both of which produced plausible but wrong
# counts (a 24-minute item passing a 60-minute floor; a kids query returning all 789 films).
# The spot checks at the bottom are therefore load-bearing, not decoration.

import csv
import re
import sys

import yaml

rows = list(csv.DictReader(open("ersatztv/audit/library-inventory.csv")))
JUNK = {"Demos", "Other videos"}
shows = {r["title"]: r for r in rows if r["kind"] == "show"}


def fields(r):
    """The fields ErsatzTV indexes, which differ by media type."""
    f = {"type": r["kind"], "library_name": r["library"], "title": r["title"]}
    mins = r["minutes"] if (r["minutes"] or "").isdigit() else None
    f["minutes"] = int(mins) if mins else None
    if r["kind"] == "episode":
        # Episodes carry no `genre` of their own; genre lives on the parent show.
        p = shows.get(r["show"])
        f["show_genre"] = set(p["genres"].split("|") if p and p["genres"] else [])
        f["show_content_rating"] = (p["content_rating"] if p else "") or ""
        f["show_title"] = r["show"]
        # An unknown field name silently evaluates False, so any query using these must have
        # them here or the clause disappears and the rating check under-counts.
        for src, dst in (("season", "season_number"), ("episode", "episode_number")):
            f[dst] = int(r[src]) if (r[src] or "").isdigit() else None
    else:
        f["genre"] = set(r["genres"].split("|") if r["genres"] else [])
        f["content_rating"] = r["content_rating"] or ""
    return f


# Bare values must not swallow a closing paren, or groups never close. The `field:(...)`
# alternative must come before the bare-value one, since a bare value cannot contain parens
# and would otherwise leave the field name unmatched and silently dropped.
TOK = re.compile(
    r'\(|\)|\bAND\b|\bOR\b|\bNOT\b|[a-z_]+:\[[^\]]*\]|[a-z_]+:\([^)]*\)'
    r'|[a-z_]+:"[^"]*"|[a-z_]+:[^\s()]+'
)

# ErsatzTV analyses the rating fields: the value is split into terms on the forward slash but
# NOT on the hyphen. Measured against the live index on 2026-11-18:
#
#   content_rating:"hu/16"            0      content_rating:(hu AND 16)      305
#   content_rating:"hu/12"            0      content_rating:12               227
#   show_content_rating:"TV-MA"     695      show_content_rating:(TV AND MA)   0
#
# So `hu/16` is the two terms `hu` and `16`, while `TV-MA` is one term `tv-ma`. That is also
# why a bare `content_rating:"12"` matches all 226 `hu/12` films: `12` is one of their terms.
# library_name and the title fields behave as exact strings instead — library_name:"TV Series"
# matches 63 shows — so term semantics are applied only to the fields where they were observed,
# rather than assumed for everything.
TERM_FIELDS = {"content_rating", "show_content_rating"}

# Fields the audit CSV cannot model, but which the schedules only ever use to NARROW a source.
# `language_tag` is the case: the CSV has no audio-language column, so it used to evaluate
# False, and every Hungarian source modelled as 0 items — a zero that passes any age ceiling,
# so check_watershed.py was checking nothing for the three -hu files.
#
# Treating such a field as satisfied instead over-approximates the source to a superset. An
# age ceiling that holds for a superset holds for every subset of it, so the ceiling verdict
# stays sound; and a superset's shortest item is no longer than the real one, so the clock in
# earliest_starts() advances no further than reality and later sources meet a ceiling at least
# as strict. Counts for affected sources are therefore upper bounds — the real numbers come
# from scripts/count_ersatztv_queries.py, which asks the live index.
#
# The argument only holds where the field is a top-level AND conjunct. Under NOT, or inside an
# OR, "assume true" no longer means "superset", so tokenize() refuses those outright rather
# than return a verdict that is quietly unsound.
OVERAPPROX_FIELDS = {"language_tag"}


def overapproximated(query):
    """True if the query's count from this model is an upper bound rather than exact."""
    return any(t.split(":", 1)[0] in OVERAPPROX_FIELDS for t in TOK.findall(query))


def value_terms(v):
    """The terms ErsatzTV indexes for a rating value. Splits on '/', keeps '-'."""
    return {t for t in re.split(r"[^0-9a-z-]+", str(v).lower()) if t}


def match_group(inner, cur):
    """Evaluate the `field:(a AND b)` form, where each word is one indexed term."""
    terms = {c.lower() for c in cur} if isinstance(cur, set) else value_terms(cur)
    res, op, neg = None, "AND", False
    for w in re.findall(r'"[^"]*"|\S+', inner):
        if w in ("AND", "OR"):
            op = w
            continue
        if w == "NOT":
            neg = True
            continue
        v = w.strip('"').lower() in terms
        if neg:
            v, neg, op = not v, False, "AND"
        res = v if res is None else (res and v if op == "AND" else res or v)
    return bool(res)


def tokenize(q):
    toks = TOK.findall(q)
    depth = 0
    for i, t in enumerate(toks):
        if t == "(":
            depth += 1
        elif t == ")":
            depth -= 1
        elif t.split(":", 1)[0] in OVERAPPROX_FIELDS:
            prev = toks[i - 1] if i else None
            nxt = toks[i + 1] if i + 1 < len(toks) else None
            if depth != 0 or prev not in (None, "AND") or nxt == "OR":
                raise ValueError(
                    "%r is only over-approximated soundly as a top-level AND conjunct, "
                    "and here it is not: %s" % (t, q)
                )
    return toks


def match_term(t, f):
    name, val = t.split(":", 1)
    if val.startswith("["):
        lo, hi = re.match(r"\[(\S+) TO (\S+)\]", val).groups()
        v = f.get(name)
        if v is None:
            return False
        return (lo == "*" or v >= int(lo)) and (hi == "*" or v <= int(hi))
    if name in OVERAPPROX_FIELDS:
        return True
    cur = f.get(name)
    if cur is None:
        return False
    if val.startswith("(") and val.endswith(")"):
        return match_group(val[1:-1], cur)
    val = val.strip('"')
    if isinstance(cur, set):
        return val.lower() in {c.lower() for c in cur}
    if name in TERM_FIELDS:
        return val.lower() in value_terms(cur)
    return str(cur).lower() == val.lower()


def evaluate(tokens, f):
    def parse(i):
        out = []
        while i < len(tokens):
            t = tokens[i]
            if t == "(":
                sub, i = parse(i + 1)
                out.append(sub)
            elif t == ")":
                # Step PAST the paren; returning i would make the caller re-read it and
                # terminate the enclosing group early, silently dropping every later clause.
                return out, i + 1
            else:
                out.append(t)
                i += 1
        return out, i

    tree, _ = parse(0)

    def ev(node):
        if isinstance(node, str):
            return match_term(node, f)
        res = None
        op = "AND"
        neg = False
        for item in node:
            if item in ("AND", "OR"):
                op = item
                continue
            if item == "NOT":
                neg = True
                continue
            v = ev(item)
            if neg:
                v = not v
                neg = False
                op = "AND"
            res = v if res is None else (res and v if op == "AND" else res or v)
        return bool(res)

    return ev(tree)


def count(query):
    return sum(
        1
        for r in rows
        if r["library"] not in JUNK and evaluate(tokenize(query), fields(r))
    )


def spot_checks():
    """Guard the parser itself. These caught two real bugs."""
    by = {(r["library"], r["kind"], r["title"]): r for r in rows}
    kids = (
        'type:movie AND (library_name:"Animated" OR library_name:"Movies") '
        "AND (genre:animation OR genre:family OR genre:children) AND minutes:[60 TO 400]"
    )
    late = (
        'type:movie AND library_name:"Movies" AND (genre:horror OR genre:thriller '
        "OR genre:mystery) AND minutes:[60 TO 400]"
    )
    cases = [
        (kids, ("Animated", "movie", "Fantasia"), True),
        (kids, ("Movies", "movie", "12 Angry Men"), False),
        (kids, ("Animated", "movie", "The Flintstones: Jogging Fever"), False),
        (late, ("Movies", "movie", "The Silence of the Lambs"), True),
        (late, ("Movies", "movie", "Carne"), False),
    ]
    failures = 0
    for q, key, want in cases:
        r = by.get(key)
        if r is None:
            continue
        if evaluate(tokenize(q), fields(r)) != want:
            print("  SPOT CHECK FAILED: %s expected %s" % (key[2], want))
            failures += 1

    # The rating-term semantics, measured against the live index. Synthetic rather than
    # title-based on purpose: these must keep holding as the library changes, and they encode
    # the behaviour that made every `hu/*` clause silently match nothing for months.
    term_cases = [
        ("content_rating:(hu AND 16)", {"content_rating": "hu/16"}, True),
        ("content_rating:(hu AND 16)", {"content_rating": "hu/18"}, False),
        # The long Hungarian variant carries both terms, so one clause covers it.
        (
            "content_rating:(hu AND 16)",
            {"content_rating": "hu/16 éven aluliak számára nem ajánlott"},
            True,
        ),
        # 6 must not match 16: `16` is one term, not a `1` and a `6`.
        ("content_rating:(hu AND 6)", {"content_rating": "hu/16"}, False),
        ('content_rating:(hu AND "PG-13")', {"content_rating": "hu/PG-13"}, True),
        ("content_rating:(hu AND KN)", {"content_rating": "hu/KN"}, True),
        # A bare value matches one term, which is how "12" reaches every hu/12 film.
        ('content_rating:"12"', {"content_rating": "hu/12"}, True),
        # Hyphens are not split, so the TV-MA failsafe was never affected.
        ('show_content_rating:"TV-MA"', {"show_content_rating": "TV-MA"}, True),
        ("show_content_rating:(TV AND MA)", {"show_content_rating": "TV-MA"}, False),
        # library_name is an exact string field, not analysed.
        ('library_name:"TV Series"', {"library_name": "TV Series"}, True),
    ]
    for q, f, want in term_cases:
        if evaluate(tokenize(q), f) != want:
            print("  SPOT CHECK FAILED: %s on %r expected %s" % (q, f, want))
            failures += 1

    # The over-approximation is only sound as a top-level AND conjunct. These pin the guard
    # that enforces it: an item with no language data must still be matched by the narrowing
    # form, and every form where "assume true" would stop meaning "superset" must be refused.
    narrowing = 'type:movie AND content_rating:"G" AND language_tag:hu*'
    if not evaluate(tokenize(narrowing), {"type": "movie", "content_rating": "G"}):
        print("  SPOT CHECK FAILED: top-level language_tag conjunct should over-approximate")
        failures += 1
    for unsound in (
        'type:movie NOT language_tag:hu*',
        'type:movie AND (content_rating:"G" OR language_tag:hu*)',
        'language_tag:hu* OR type:movie',
    ):
        try:
            tokenize(unsound)
        except ValueError:
            continue
        print("  SPOT CHECK FAILED: guard accepted an unsound form: %s" % unsound)
        failures += 1

    print("spot checks: %s" % ("pass" if not failures else "%d FAILED" % failures))
    return failures == 0


def main():
    ok = spot_checks()
    for fn in ("main.yml", "kids.yml", "movies.yml"):
        path = "ersatztv/%s" % fn
        doc = yaml.safe_load(open(path))
        print("\n=== %s ===" % fn)
        keys = set()
        for c in doc["content"]:
            keys.add(c["key"])
            # A marathon carries `searches` rather than `query`, and the source is the UNION
            # of them, so counting only the first would under-report. Summing is close enough
            # here because the searches in these files are written to be disjoint.
            queries = c["searches"] if "searches" in c else [c["query"]]
            n = sum(count(q) for q in queries)
            if not n:
                ok = False
            print("  %-16s %5d items%s%s" % (c["key"], n,
                                             "  (%d searches)" % len(queries) if len(queries) > 1 else "",
                                             "" if n else "   <-- EMPTY, would be dead air"))
        refs = set(re.findall(r'content:\s*"([A-Z_]+)"', open(path).read()))
        missing = refs - keys
        if missing:
            print("  UNRESOLVED REFERENCES: %s" % sorted(missing))
            ok = False
        else:
            print("  all %d playout references resolve" % len(refs))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
