# TV station change log

Copied from the HA repo's docs/logs/changes-tracker.md on 2026-11-20, when the TV station work moved
out of HA. Only the ErsatzTV / Plex / schedule entries are here; the full history, including the
commits, is on the HA repo's `ersatztv-archive` branch. New entries go at the end.

## 2026-09-24 — ErsatzTV: episode genre queries were broken; ratings investigated

**Bug found and fixed.** While answering a question about whether Plex ratings were usable, I
pulled ErsatzTV's complete search field reference and found that **episodes have no `genre`
field** — only `show_genre`. Every episode query in the three schedules used `genre:`, which
matches nothing. This fails silently: no error, no warning, just an empty content source. Had
these deployed as written, `FAMILY_SHOWS`, `DAYTIME_COMEDY`, `EVENING_DRAMA` and `NATURE`
would all have resolved to zero items, blanking most of the Main channel and the afternoon of
the Kids channel. Rewrote all five affected queries to `show_genre:`. Movie queries correctly
keep `genre:` and were left alone.

**Fail-safe added.** The same reference showed `show_content_rating` is a valid episode field,
so every family-safe source on both the Kids and Main channels now carries
`NOT show_content_rating:"TV-MA"`. Previously the only thing keeping adult animation out of
the 06:00 block was library hygiene plus the observation that Archer lacks a `family` genre.
Now a mis-tagged show is excluded on two independent grounds.

**Ratings: available in Plex, not queryable in ErsatzTV.** ErsatzTV indexes no critic,
audience, or personal score for any media type — `content_rating` (the age classification) is
the only rating-like field it has. Plex does hold real scores with good coverage, now captured
by the audit: audience rating on 776 of 790 films (98%, median 7.9), critic on 714 (90%,
median 7.7), personal on 2. At an audience threshold of >= 8 there are 377 films; >= 9 gives
175, critic >= 8 gives 322.

The usable route is indirect, since `collection` **is** searchable and Plex collections sync:
build a Plex smart collection filtered on rating, then match it with `collection:"Top Rated"`.
Documented as a worked, deliberately not-yet-enabled recipe at the bottom of `movies.yml` —
enabling it before the Plex collection exists and has synced would produce dead air.

**Files touched:** `ersatztv/main.yml`, `ersatztv/kids.yml`, `ersatztv/movies.yml`,
`ersatztv/README.md`, `scripts/plex_library_audit.py`, `docs/logs/changes-tracker.md`.

## 2026-09-24 — ErsatzTV: itemised the metadata gaps, and found ten films that aren't films

Counts were not actionable, so the audit now names every title with a gap. Two new sections
in `ersatztv/audit/library-audit.txt`, plus `file` and `size_mib` columns in the CSV
(basenames only — full paths are deliberately not recorded).

**The headline is not a metadata gap.** Ten titles in the Movies library are **sample clips**,
not films: The Godfather, The Silence of the Lambs, Rain Man, Gran Turismo, Everything
Everywhere All at Once, The Magnificent Seven, Flight of the Phoenix, Star Wars: Return of the
Jedi, Summer of '42 and one Hungarian title. Verified against Plex — the backing files are
literally named `*.Sample.mkv` / `sample.mkv`, 70 seconds to 3 minutes long. Plex matched them
to the real film, so they carry the correct title, poster, year and ratings and look entirely
healthy in the UI. Duration is the only tell, and ErsatzTV would have scheduled The Godfather
into a two-hour prime slot where it ended after 70 seconds.

**Guard added.** Every film source across all three schedules now carries
`minutes:[60 TO 400]`. That keeps 770 of 790 films and makes it impossible for a sample to
reach air. The 20 excluded are the 10 samples, 3 probable partial rips (The Number 23 at 34
min, O Brother Where Art Thou at 51, Midnight Masquerade at 48), and genuinely short titles
that do not belong in a feature slot anyway (A Trip to the Moon at 13 min, two IMAX
documentaries). The upper bound is generous — the longest real film here is 263 min.

**Duplicates.** `Carne` and `The Flesh` are two Plex entries pointing at one 581 MiB file;
one of the two matches is wrong. Four titles exist in both Animated and Movies (Fantasia,
Fantasia 2000's intro clip, Pooh's Grand Adventure, and one release-named file). The
same-file check is keyed on name *and* size, because Blu-ray folder rips all share basenames
like `00000.m2ts` and were otherwise flagged as six false positives.

**Metadata gaps proper.** 25 of 790 films and 4 of 48 shows have at least one gap. Twelve
films are simply **unmatched in Plex** — no genre, no certificate, no audience score at all —
so one "Fix Match" per title repairs every field at once rather than needing manual tagging.
Most are ambiguous titles Plex could not resolve: `9`, `Home`, `Robin Hood`, `Gia`, `The
Beach`, `Bottle Rocket`, `All That Jazz`, `A tanu`. The remaining eleven lack only a content
rating, which costs nothing here since scheduling is by genre. One show is unmatched — *Me
and Winnie the Pooh*, whose folder is still a release name — and it takes all 25 of its
episodes out of genre reach.

Critic ratings are absent on all 48 shows; that is normal, Plex does not carry critic scores
for TV, and it is not a fixable gap.

**Files touched:** `scripts/plex_library_audit.py`, `ersatztv/main.yml`, `ersatztv/kids.yml`,
`ersatztv/movies.yml`, `docs/logs/changes-tracker.md`.

## 2026-09-24 — Kometa installer, with genre rewriting deliberately disabled

Added `scripts/install_kometa_plex_vm.sh` — Kometa (formerly Plex Meta Manager) as an
on-demand Docker container on the Plex VM, for normalising metadata that is inconsistent
rather than absent.

**The operation worth having is `mass_content_rating_update: mdb_commonsense`.** Plex holds
Hungarian certificates (`hu/16`, `hu/12`, `hu/KN`, `hu/6`, `hu/14`, `hu/18`) which ErsatzTV can
only match as opaque case-sensitive strings — this is what pushed the schedules onto genre
filtering. Rewriting them all from Common Sense Media via MDBList gives plain numbers, so
`content_rating` becomes schedulable and the kids channel can have a real age gate instead of
inferring safety from genre.

**`mass_genre_update` is off by default, behind `--enable-genre-update`.** It was requested,
but checking it against the library first showed it would be a downgrade. It replaces rather
than fills, and these genres are richer than TMDb's fixed vocabulary. Enabling it erases
`biography` (33 films), `musical` (19), `short` (4), `children` (3) and `sport` (2) from the
movie library; on the TV side TMDb uses compound genres like "Action & Adventure" and 11 of
the 17 genres in use would be lost. `genre:children` appears in the `KIDS_MOVIES` query, so
the schedules would need re-tuning too.

It also would not fix the titles that actually lack a genre. Those 12 films and 1 show are
unmatched in Plex, so they have no GUID for Kometa to look anything up by. Fixing the match
makes Plex's own agent fill the genres itself, in the richer vocabulary — Kometa is simply the
wrong tool for that job, and the header says so.

**Safety properties.** The installer changes nothing in Plex; the first run is manual by
design. It refuses to run on the Proxmox host, verifies Plex is answering on loopback before
touching anything, and requires Docker from the ErsatzTV installer rather than duplicating
that logic. Credentials are read from `~/.plex_token`, `~/.tmdb_key` and `~/.mdblist_key` in
the invoking user's home (resolved via `SUDO_USER`, since sudo rewrites `$HOME`) and are never
echoed; `config.yml` lands at 0600 outside the repo. `kometa.timer` is installed but left
disabled until a canary run on the 4-item Animated library has been eyeballed. The container
has no restart policy and no internal scheduler, so it never idles holding a Plex connection,
and it reaches Plex over the Docker host gateway rather than host networking — which also
keeps the script free of any hard-coded address.

**Verified:** POSIX syntax clean, shellcheck clean, the sudo flag re-pass produces correct
argv for all four flag combinations in `sh`/`dash`/`bash` (the `&&` guards do not trip
`set -e`), a missing or empty credential file aborts before any write, and the generated
`config.yml` parses as valid YAML in both genre modes with library names matching Plex
exactly (`Movies`, `TV Series`, `Cartoons`, `Animated`; `Demos` and `Other videos` excluded).

**Files touched:** `scripts/install_kometa_plex_vm.sh`, `.gitignore`,
`docs/logs/changes-tracker.md`.

## 2026-09-24 — Kometa installer made host-agnostic; it belongs on the NAS LXC

Renamed `install_kometa_plex_vm.sh` to `scripts/install_kometa.sh` and taught it to run on
either the NAS LXC or the Plex VM.

**The original placement was reasoned from a false premise.** I put it on the Plex VM by
analogy with ErsatzTV, but the analogy does not hold: ErsatzTV opens media files, which is why
sharing the VM mattered there (identical `/mnt/media`, no Path Replacements). Kometa never
opens a media file — it is purely a Plex API client, reading and writing metadata over HTTP
and looking titles up on TMDb and MDBList. Where the media lives is irrelevant to it.

**The NAS LXC is in fact the better host.** The Plex VM is the one under CPU pressure, running
Plex alongside ErsatzTV which transcodes on CPU only. A weekly metadata pass has no reason to
compete for that.

**What the script now does.** Plex is located automatically: loopback first, then
`plex.internal`, with `--plex-url` as an override. A local Plex gets a `host.docker.internal`
host-gateway alias in the compose file, since a container cannot use the host's 127.0.0.1; a
remote Plex is addressed by hostname and the alias is omitted. Using the existing internal DNS
name means the script contains no IP address at all, unlike the two earlier ones.

A pre-flight check now probes `api.themoviedb.org` and `api.mdblist.com` before anything is
written. This is aimed squarely at the NAS LXC: rule 11 blocks VLAN 30 from WAN unless the host
is whitelisted in rule 10, and Kometa refuses to start without TMDb, so a blocked host fails in
a way that reads like a bad API key rather than a firewall. The check treats a non-2xx response
as success, since only a connection failure proves unroutability.

The completion notice now warns about the MDBList quota: a free key allows 1000 requests a day
and a full run needs roughly 840, so the 4-request canary matters.

**Documentation drift, confirmed by the user and still unfixed.** `topology.md` rule 10 lists
only three hosts as WAN-permitted on VLAN 30, and rule 11 names the NAS as blocked — but the
*arr stack runs on the NAS LXC and reaches indexers, so rule 10 must have been
widened. `Home_Network_Reference_v8.md` also still lists the *arr stack as an unchecked
"consider" item. That is the third drift found in this thread, after the Plex LXC-versus-VM
discrepancy.

**Verified:** POSIX syntax and shellcheck clean; argument parsing correct for five input
combinations including both `--plex-url URL` and `--plex-url=URL`, and rejecting a valueless
`--plex-url` and unknown flags; the sudo re-exec carries all three options through; the
generated compose and config parse as valid YAML in both local and remote modes, with the
host-gateway alias present only when Plex is local.

**Files touched:** `scripts/install_kometa.sh` (renamed), `docs/logs/changes-tracker.md`.

## 2026-09-24 — Audio and subtitle language selection; the library is largely untagged

Added `ersatztv/stream-selector-hu.yml` and `ersatztv/stream-selector-en.yml`, prioritised
audio/subtitle selectors for a Hungarian-preferring and an English-preferring channel. They
deploy to `/opt/ersatztv/config/scripts/channel-stream-selectors/` and are chosen per channel
by setting `Stream Selector Mode` to Custom.

**ErsatzTV does select streams, two ways.** In Default mode a channel filters by Preferred
Audio Language and Preferred Audio Title, then takes the default-flagged stream or the one
with the most channels; subtitles follow a Subtitle Mode of None/Forced/Default/Any plus a
Preferred Subtitle Language. Custom mode replaces that with a YAML list of items tested top to
bottom, where audio and subtitle criteria must both be satisfied within a single item.

**The finding that shapes the design: much of this library has no audio language tag.**
Measured against Plex's own language filters:

| Library | Items | hu audio | en audio | untagged (at least) |
|---|---|---|---|---|
| Movies | 785 | 335 | 545 | 207 |
| TV Series episodes | 2584 | 496 | 877 | 1211 |
| Cartoons episodes | 422 | 32 | 51 | 339 |

Cartoons are 80% untagged. So building language-specific channels by *filtering titles* with
ErsatzTV's `language:` search field would be a trap — a Hungarian cartoon channel would see 32
of 422 episodes. The better design is the opposite: let both channels draw from the full
catalogue and differ only in their stream selector. 302 films carry both a Hungarian and an
English track, so they can legitimately air on either channel with the right audio chosen; 243
are English-only and 33 Hungarian-only.

Both selector files therefore end in a `audio_language: ["*"]` catch-all, which is what covers
the untagged majority; without it those items would have no audio stream selected at all.

**Verified:** both files parse as valid YAML, use only documented keys, every item makes an
explicit subtitle decision (`subtitle_language` or `disable_subtitles`), and the final item is
a genuine catch-all.

**Unverified assumption, flagged in the files:** whether `audio_language: ["*"]` matches a
stream whose language tag is null is not stated in the docs. It is the documented catch-all
idiom so it should, but with ~340 untagged cartoon episodes riding on it, this is worth
confirming with ErsatzTV's playback troubleshooting tool, which has a Stream Selector option
for testing behaviour against specific content.

**Files touched:** `ersatztv/stream-selector-hu.yml`, `ersatztv/stream-selector-en.yml`,
`docs/logs/changes-tracker.md`.

## 2026-09-24 — Pre-deployment validation; two parser bugs in my own checker

Added `scripts/validate_ersatztv_queries.py`, which checks the three schedules against the
CSV from the library audit. It catches the two failures ErsatzTV does not warn about: a content
source that matches nothing (dead air), and a `content:` reference with no matching key.

**The validator was wrong twice before it was right, and both bugs produced believable
numbers** — which is the reason it now carries spot checks that assert known-good and
known-bad items rather than just printing totals.

1. The tokenizer used `[a-z_]+:\S+` for bare values, and `\S` matches `)`. So
   `genre:children)` consumed the closing paren, the group never closed, and operator grouping
   collapsed. Fixed with `[^\s()]+`.
2. On reaching `)` the parser returned the index *at* the paren instead of past it, so the
   caller re-read it and terminated the enclosing group immediately. Every clause after the
   first `(...)` group was silently discarded. This is why `KIDS_MOVIES` reported all 789
   films and a 24-minute Flintstones episode passed a `minutes:[60 TO 400]` floor. Fixed by
   returning `i + 1`.

Counts reported in earlier entries for queries with a parenthesised group followed by further
clauses were therefore understated or overstated. Corrected figures, all sources non-empty:

| Schedule | Source counts |
|---|---|
| main.yml | CARTOONS 422, FAMILY_SHOWS 246, DAYTIME_COMEDY 1418, EVENING_DRAMA 1516, FEATURE_FILM 731, LATE_NIGHT 140 |
| kids.yml | CARTOONS 422, SHORT_CARTOONS 361, FAMILY_SHOWS 221, NATURE 25, KIDS_MOVIES 54 |
| movies.yml | MATINEE 186, ACTION 255, COMEDY 242, PRIME_DRAMA 417, LATE_GENRE 59, SHORT_FILMS 182 |

**Library state after the user's fixes.** Genre gaps fell from 11 films to 3, of which two are
files still awaiting deletion (the 3-minute `Fogd a pénzt és fuss` sample and the Flintstones
episode duplicated into Movies) and one is a legitimately unmatched IMAX documentary. The
`Me and Winnie the Pooh` show is still unmatched and still costs 25 episodes. Movies content
ratings remain Hungarian, so Certification Country has not been changed yet — harmless, since
nothing queries `content_rating`.

**ErsatzTV state.** Confirmed running: `/iptv/channels.m3u` serves only the stock channel 1,
so no custom channels exist yet. `/api/libraries` and `/health` return the SPA HTML rather than
JSON, so library sync status could not be confirmed remotely.

**Open question for deployment:** the published docs do not state which config subfolder
sequential schedule files belong in, and the hook blocks SSH to that host so the directory
could not be listed. Stream selectors are documented as `config/scripts/channel-stream-selectors`
and scripted schedules mount at `/app/scripted-schedules/scripts`, so the sequential folder is
adjacent, but this needs one `ls` on the host to confirm rather than a guess.

**Files touched:** `scripts/validate_ersatztv_queries.py`, `docs/logs/changes-tracker.md`.

## 2026-10-02 — ErsatzTV deployed; `custom_title` was hiding every film name

The three sequential schedules and two stream selectors went onto the Plex VM and six channels
are now live in Plex. Config folder is `/opt/ersatztv/config`, confirmed by `docker inspect`
rather than guessed — the earlier `find: '/opt/ersatztv/config': No such file or directory` was
run on the Proxmox host instead of inside the guest. Resolved the open question from the
previous entry: schedules have no mandated folder (the path is typed into the playout), so they
live in `/config/sequential-schedules/`; selectors are in the documented
`/config/scripts/channel-stream-selectors/`. Image is `ghcr.io/ersatztv/legacy:latest` at
26.8.0, which is the maintained line — the original project was archived, then unarchived as
`ErsatzTV Legacy`, while `ErsatzTV Next` is a Rust rewrite that deliberately excludes
scheduling and library management and so cannot run this setup at all. Channel `Streaming
Engine` left on `Legacy`; the bundled Next engine is 0.1.0 and had a subtitle playback bug
fixed only in 26.6.0, which matters because the whole language design leans on subtitles.

**Removed all four `custom_title` lines** — `Evening Film` (main), `Family Film` (kids),
`Matinee` and `Prime Feature` (movies). These replace the displayed title outright, so Plex's
guide showed "Family Film" instead of *Fiddler on the Roof*. It also produced an apparent bug
that wasn't one: the HU and EN channels both printed the same label at the same time while
airing different films, because each channel has its own independently shuffled playout.

**Transcoding reality, corrected.** I claimed the VM's CPU had SSE4 and AES masked off, inferring
that from the `QEMU Virtual CPU version 2.5+` model string. The type is actually
`x86-64-v2-AES`, which includes SSE4.1, SSE4.2 and AES-NI; only the v3 set (AVX2, FMA, BMI) is
missing. So switching to CPU type `host` is worth roughly ten percent, not the multiples I
first estimated, and **core count is the real constraint** — the VM has 2. There is no GPU:
`/dev/dri` inside the container is absent, and on the VM it holds only `card0` with no render
node, i.e. the virtual display adapter, not a passthrough device.

Hardware acceleration cannot be avoided by configuration here. Plex only supports ErsatzTV via
MPEG-TS (HDHomeRun emulation), and MPEG-TS is a wrapper over the HLS Segmenter, which
transcodes. The one non-transcoding mode, HLS Direct, does not work with Plex. Profile is
therefore software h264 at 720p, `veryfast`, AAC stereo, 8-bit. User chose **not** to cap
resolution, so the 184 4K films stay in rotation and will stutter; `Normalize Colors` is the
first thing to disable when they do, since HDR tonemapping on CPU is the dominant cost.

**Language handling.** Six channels now exist — three EN, three HU — sharing the same three
schedules with different stream selectors. Confirmed this cannot make the HU channels
Hungarian-only: a selector picks a track within a file and has no influence on which files are
scheduled. Verified from the search docs that `language_tag` and `sub_language_tag` are
available on episodes as well as movies, so query-level filtering is possible. Not applied yet,
because roughly 340 of 422 cartoon episodes carry no audio language tag and a `language_tag:hu*`
filter would exclude them all — untagged is not the same as not-Hungarian. Awaiting result
counts from ErsatzTV's search box before building HU-specific schedule files.

**Files touched:** `ersatztv/main.yml`, `ersatztv/kids.yml`, `ersatztv/movies.yml`,
`docs/logs/changes-tracker.md`.

## 2026-10-02 — Hungarian schedules: filter the dialogue, leave the slapstick alone

Added `main-hu.yml`, `kids-hu.yml` and `movies-hu.yml` so the three HU channels have their own
catalogues rather than sharing the English ones. Confirmed first that sharing could never work:
a stream selector picks a track inside a file it has already been given and has no influence
over which files are scheduled, so `stream-selector-hu.yml` alone can only fall down its
fallback chain and play English. Verified from the search field reference that `language_tag`
and `sub_language_tag` exist on episodes as well as movies, which is what makes query-level
filtering possible at all. The `hu*` wildcard is mandatory — the library mixes `hu` and `hun`.

**Measured counts** from ErsatzTV's own search index: 375 of 786 films carry Hungarian audio
(684 with audio *or* Hungarian subtitles), 57 of 422 cartoon episodes, and 560 TV episodes
with audio or subtitles. User chose dubbed-only for Main and Movies.

**The cartoon sources are deliberately left unfiltered**, and this is the one decision worth
recording. Roughly 340 of the 422 cartoon episodes carry no audio language tag, and the user
identified why: they are largely dialogue-free — Tom and Jerry, Dexter shorts. There is nothing
in them to dub, so they belong equally on either channel. Applying `language_tag:hu*` would cut
422 episodes to 57 and destroy an eight-hour morning block to solve a problem those files do not
have. Cost accepted: ~25 English-tagged cartoon episodes will air on the HU channels. The
documented alternative, `NOT language_tag:en*`, is noted in the file but not applied, because it
also drops dual-audio files that do contain a Hungarian track.

Everything carrying speech is filtered: FAMILY_SHOWS, NATURE, KIDS_MOVIES, DAYTIME_COMEDY,
EVENING_DRAMA, FEATURE_FILM, LATE_NIGHT and all six movie sources.

**Not yet verified, and flagged in the files themselves.** Movies is safe — 48% of the library
is dubbed, so every genre block keeps about half its English counterpart, comfortable everywhere
except LATE_GENRE which lands near 30. The risk is `main-hu.yml`: the dubbed-only counts for the
three TV sources are unknown, only the 560 audio-or-subtitles figure is, and those three sources
carry 09:00–20:00. An empty content source is dead air rather than a build error, so the headers
instruct verification before deployment and give the one-line widening to
`(language_tag:hu* OR sub_language_tag:hu*)` if they prove too thin.

**Process note:** the three files initially failed to parse because I wrote inline line-number
prefixes (`    10|`) into their contents. Caught by the YAML validation step, stripped, re-checked.

**Files touched:** `ersatztv/main-hu.yml`, `ersatztv/kids-hu.yml`, `ersatztv/movies-hu.yml`,
`docs/logs/changes-tracker.md`.

## 2026-10-02 — HU schedules finished against measured counts; the family block had no pool

Verified every Hungarian content source against ErsatzTV's search index and fixed the two that
could not survive the filter. All sources in all six schedules are now backed by a real count.

**Measured:** 28 dubbed kids' films, 46 dubbed horror/mystery films, comedy and drama both
plentiful dubbed. The outlier was `show_genre:family AND language_tag:hu*` — **six episodes of
a single show** in the entire library, against a three-hour daily slot on two channels.

**main-hu.yml — removed the family block entirely.** Daytime comedy now runs 09:00–17:00 instead
of 12:00–17:00. Chosen over widening to `(language_tag:hu* OR sub_language_tag:hu*)` so the
channel stays genuinely dubbed throughout rather than part-subtitled. The `FAMILY_SHOWS` content
source was deleted along with its playout instruction; a validation pass confirms no orphaned
references and no unused sources remain.

**kids-hu.yml — left FAMILY_SHOWS and NATURE unfiltered.** Subtitles are not an option for young
children, so the real choice was an English *7th Heaven* or no afternoon block at all. English
won. `KIDS_MOVIES` remains the one filtered source on that channel, which is where dubbing
matters most and is achievable at 28 films. This also made the outstanding
`documentary AND family AND language_tag:hu*` count moot — NATURE keeps all 25 episodes
regardless of which show those six Hungarian episodes belonged to.

Net effect: the HU channels are dubbed wherever a dubbed pool exists, and fall back to the
language-neutral or English pool only where the alternative was dead air. Every such fallback is
documented in the file that makes it, with the one-line change to reverse it if the library grows.

**Files touched:** `ersatztv/main-hu.yml`, `ersatztv/kids-hu.yml`, `docs/logs/changes-tracker.md`.

## 2026-10-02 — 18:00 watershed enforced on all six channels, and machine-checked

User requirement: nothing rated 12+ before 18:00 on any channel. Implemented as rating
**allow-lists**, never exclusions, and verified by a new script rather than by reading YAML.

**Why allow-lists.** `NOT show_content_rating:"TV-MA"` is TRUE for an item with no rating, and
this library contains unrated adult drama — *Terapia* (40 episodes) and *The Fear Index* (4)
carry no content rating at all and sailed through the old exclusion-based filters. The movie
side is worse: 36 films are unrated or "Not Rated", and the Hungarian values are inconsistent
(`hu/16` also appears with a trailing space and once as
`hu/16 éven aluliak számára nem ajánlott`). An allow-list fails closed and never has to
enumerate the unsafe side.

**Violations that existed before this change**, all now closed: Main ran `show_genre:comedy`
unfiltered at 12:00–17:00, which included *Archer* and *Californication* (TV-MA) plus seven
TV-14 sitcoms; Main ran unrestricted drama from 17:00, admitting *Game of Thrones* and
*Breaking Bad* an hour before the watershed; the Movies channel ran action films from 13:00.

**Permitted pre-watershed.** TV: TV-G, TV-Y, TV-Y7, TV-PG. Film: G, hu/KN, hu/6. The user chose
the strict reading on film and excluded PG, taking the pool from 52 to 37. TV-PG is load
bearing rather than a concession — TV-G and TV-Y7 alone yield **zero** comedy episodes, so the
daytime block would not exist without it. It admits only Big Bang Theory, Friends, Northern
Exposure, Georgie & Mandy and Showder Klub.

**Structural consequences.** Main gained an `EARLY_DRAMA` source (483 safe episodes) so
17:00–18:00 is restricted while 18:00–20:00 stays unrestricted. The Movies channels could not
keep genre dayparts at all — only 6 of 255 action films are under 12 — so `MATINEE` was replaced
by a single `FAMILY_FILMS` pool of 37 films running 09:00–18:00, with the genre schedule
starting at the watershed and `ACTION` moved after prime time to keep it in rotation. Kids
channels: family shows moved to the allow-list, and the 18:00 feature was restricted to 19
films even though 18:00 itself is not pre-watershed, because a children's channel should not
air a 12+ film at any hour.

**The Cartoons library is the one deliberate exemption.** `Me and Winnie the Pooh` carries no
rating, so an allow-list would silently drop its 25 episodes. All other shows in that library
are verified TV-G or TV-Y7, so the guard there remains library hygiene, as already documented.
The checker reports those 25 as `review` rather than passing them silently.

**New: `scripts/check_watershed.py`.** Walks each playout, determines which sources are
reachable while the clock is before 18:00 (counting `fallback` as reachable, and treating
`count` instructions conservatively), evaluates their queries against the audit CSV and fails
on any 12+ match. Reuses the evaluator from `validate_ersatztv_queries.py`. Current verdict:
**no 12+ content is reachable before 18:00 on any channel**, exit 0. Its figures independently
reproduced the hand analysis — FAMILY_SHOWS 246, DAYTIME_COMEDY 664, EARLY_DRAMA 483,
FAMILY_FILMS 37.

**Documented blind spot:** the audit CSV has no audio language column, so language-filtered
sources report 0 items. The three HU schedules therefore show 0 for their daytime sources, which
proves nothing either way about emptiness and must be checked in ErsatzTV's search box. The
safety verdict still holds for them by subset reasoning, since each HU query is its EN
counterpart plus a conjunction.

**Files touched:** `ersatztv/main.yml`, `ersatztv/main-hu.yml`, `ersatztv/kids.yml`,
`ersatztv/kids-hu.yml`, `ersatztv/movies.yml`, `ersatztv/movies-hu.yml`,
`scripts/check_watershed.py`, `docs/logs/changes-tracker.md`.

## 2026-10-03 — HU daytime sized against measured dubbed pools

Verified the three language-filtered pre-watershed sources in ErsatzTV (the audit CSV cannot
answer this, having no language column): dubbed and under-12-safe comedy is **56 episodes**,
early drama **27 episodes**, family films **4 films**.

Early drama needs no change — 27 episodes against one hour a day is about three weeks.

**main-hu.yml: cartoon block extended 09:00 → 10:30.** 56 episodes is roughly 20 hours, which
repeats every two and a half days over an eight-hour comedy block and about three over six and
a half. The cartoons absorb the difference at no cost, being language-neutral and 422 deep. The
header records the reasoning and says to move it back toward 09:00 as the dubbed pool grows.

**movies-hu.yml: the four-film daytime loop is kept deliberately.** User's call, pending a
metadata cleanup pass. Four films is about seven hours against a nine-hour block, so the
daytime repeats daily. Documented at length in the file precisely so a future reader does not
"fix" it by widening the query: the cause is that 207 films carry no audio language tag, and the
one-line escape (dropping `AND language_tag:hu*` for all 37 under-12 films) is written down
next to it.

Watershed check still passes: no 12+ content reachable before 18:00 on any channel.

**Files touched:** `ersatztv/main-hu.yml`, `ersatztv/movies-hu.yml`,
`docs/logs/changes-tracker.md`.

## 2026-10-03 — 104 TV-G episodes were unreachable; forced English subtitles

**`How It's Made` had never aired.** 104 episodes, rated TV-G, carrying `documentary` as its
ONLY genre — and not one of the eighteen content sources across six schedules could match it.
Main had no documentary query at all, and the kids' nature block required
`documentary AND family`, which excludes it. Found while answering the user's question about
why documentaries were not filling the daytime; their expectation was correct and the
schedules were wrong.

Added `DAYTIME_DOCS` to `main.yml` (129 episodes: How It's Made 104 plus Planet Earth I/II/III
25) in a new 12:00–14:00 block, which also shortens the comedy block from five hours to three
and slows how fast that pool cycles. *The Grand Tour* stays excluded, being TV-14.

Widened `NATURE` on both kids schedules by dropping the `family` genre requirement and relying
on the rating allow-list instead: 25 → 129 episodes. The genre was never what made that block
safe; the ratings are.

**NOT added to `main-hu.yml`.** The dubbed documentary count is unknown and a 12:00–14:00 block
backed by an empty source is dead air. Needs verifying in ErsatzTV first:
`type:episode AND library_name:"TV Series" AND show_genre:documentary AND language_tag:hu* AND (...allow-list)`

**`stream-selector-en.yml` rewritten to force English subtitles.** Previously every English
audio match set `disable_subtitles: true`. Now each language tier requests English subtitles
with a no-subtitle twin immediately below it — six items instead of three. The twins are
structural, not redundancy: audio and subtitle criteria must both match within one item, so
without them, content with English audio but no English subtitle track would fall through to
the catch-all and lose its audio preference as well. Documented in the file that MPEG-TS burns
subtitles in, and that embedded text subs additionally need the global extraction setting.

**Diagnosed, not a fault:** user reported *Top Gear* in the EPG while *Northern Exposure*
played. Northern Exposure is correct for the new daytime pool. Top Gear is not in the library
snapshot at all, and the nearest title (*The Grand Tour*) is matched by no query, so the EPG
entry is a stale playout plus Plex's cached guide — same root cause as the lingering "Matinee"
label. Fix is Reset All Playouts followed by Refresh Guide in Plex, not a schedule change. Also
established there is no National Geographic content in the TV Series library.

Watershed check still passes, now covering 5 pre-watershed sources on main.yml.

**Files touched:** `ersatztv/main.yml`, `ersatztv/kids.yml`, `ersatztv/kids-hu.yml`,
`ersatztv/stream-selector-en.yml`, `docs/logs/changes-tracker.md`.

## 2026-10-03 — 385 episodes were airing nowhere; eleven orphaned shows recovered

Asked where Top Gear and The Grand Tour sat, which turned into an audit of what no query can
reach. Answer for The Grand Tour: nowhere. Top Gear is not in the snapshot at all. Eleven shows
totalling **385 episodes** were unreachable by any of the eighteen content sources.

**I caused roughly three quarters of it.** The watershed allow-list correctly removed TV-14 and
TV-MA comedy from the noon slot, but Main had no post-watershed comedy source — its only evening
TV block was drama and crime. So Two and a Half Men (188), Archer (75), Joey (24) and Coupling
(6) went from airing at the wrong time to not airing at all. Recorded plainly because it is the
second time in this project that a correct-looking filter silently emptied something.

The rest predates any change here: no query had ever used the action, adventure, war, history,
science fiction, fantasy or reality genres, so The Mandalorian, Halo, Strike Back, Masters of
the Air, Moon Knight and The Grand Tour had never been schedulable.

**Fix, on both Main channels.** Added `EVENING_COMEDY` (unrestricted comedy, 1704 episodes) at
18:00–19:00, and widened `EVENING_DRAMA` from `drama OR crime` to also cover action, adventure,
thriller, war, history, `"science fiction"`, fantasy, mystery and reality. The quoted phrase
matters — `science fiction` contains a space.

**Requested as "comedy from 17:00", implemented as comedy from 14:00.** A literal reading would
have put Archer and Two and a Half Men on screen at 17:00, breaking the user's own 12+ rule. So
comedy now runs continuously from 14:00 and changes *pool* rather than genre at the watershed:
rating-restricted `DAYTIME_COMEDY` until 18:00, unrestricted `EVENING_COMEDY` after. `EARLY_DRAMA`
was dropped from main.yml as a consequence, since its 17:00–18:00 slot became comedy. It is
**kept in main-hu.yml** deliberately: that channel's dubbed comedy pool is only 56 episodes and
needs the variety more than it needs the symmetry.

Verified after the change: **0 orphaned shows, 0 orphaned episodes.** Watershed check still
passes, now with 4 pre-watershed sources on main.yml.

**Still open:** animated films rated `hu/12` and above — Toy Story 3, Mufasa, The Lion King —
remain unschedulable. Replacing `MATINEE` with the under-12 `FAMILY_FILMS` pool removed their
only slot, and Main's `FEATURE_FILM` excludes animation outright. The Lion King being tagged
`hu/18` is also a Plex metadata error. User has not yet chosen a fix.

**Files touched:** `ersatztv/main.yml`, `ersatztv/main-hu.yml`, `docs/logs/changes-tracker.md`.

## 2026-10-03 — Main rebuilt on four loose mixed blocks instead of seven tight ones

Requested layout: cartoons 06–10, a family/documentary/kid-comedy mix 10–15, a family/comedy
mix 15–18, comedy plus broad genres with nothing above 16 from 18–20, feature at 20:00, late
night at 23:00. Applied to both `main.yml` and `main-hu.yml`.

**How a mix is built.** A sequential schedule draws each instruction from exactly one content
source, so there is no way to tell one `pad_until` to alternate between three sources. Mixing
is done by OR-ing the genres inside a single query and shuffling, which interleaves them
properly. The trade-off is that proportions follow pool size rather than intent — the 10:00
block is roughly two thirds comedy because that is what the library holds. Controlling the
ratio is exactly what the previous, tighter dayparting did; the looser version trades that
control for variety.

**Seven sources became five.** `FAMILY_SHOWS`, `DAYTIME_DOCS` and `DAYTIME_COMEDY` collapsed
into `DAYTIME_MIX` (992 episodes) and `AFTERNOON_MIX` (888, the same minus documentaries).
`EVENING_COMEDY` and `EVENING_DRAMA` collapsed into `EVENING_MIX` (2060) and `NIGHT_TV` (2455).

**"Nothing 16+" is a second allow-list, not an exclusion.** 18:00–20:00 permits TV-G, TV-Y,
TV-Y7, TV-PG and TV-14 — one notch looser than the pre-watershed list, still fails closed on
unrated. So early evening is open to Gilmore Girls, HIMYM, Two and a Half Men and The Grand
Tour but not Game of Thrones or Archer.

**The 20:00–23:00 block is load bearing and must not be tightened.** 395 episodes sit above
TV-14 (Californication 84, Archer 75, Game of Thrones 68, the unrated Terapia 40, and eleven
more). `NIGHT_TV` after the feature film is now their only home on the channel. Removing or
rating-capping that block would strand all 395 — the same trap that stranded 385 episodes
earlier today.

Verified: all six schedules parse, every content source is referenced, no source is unused,
**0 orphaned shows**, and the watershed check still passes with three pre-watershed sources
on Main (cartoons 422, daytime mix 992, afternoon mix 888).

**Films: 15 unreachable, 12 of them correctly so.** The `minutes:[60 TO 400]` floor is doing
its job on shorts and junk — a 3-minute sample, a 24-minute clip, A Trip to the Moon (13 min),
the Flintstones short, two IMAX fragments, Carne and The Flesh (38 min each, and a known
shared-file duplicate pair). Star Wars Episode VI reports 0 minutes and is the known stub.
That leaves **Toy Story 3, Mufasa and The Lion King** genuinely homeless: animation is excluded
from Main's feature film source and the Movies channel's daytime pool is capped under 12.
Still awaiting a decision on those three. The Lion King's `hu/18` rating is a Plex error.

**Files touched:** `ersatztv/main.yml`, `ersatztv/main-hu.yml`, `docs/logs/changes-tracker.md`.

## 2026-10-03 — Movies channel moved to a three-step age ladder; animation admitted

Requested: no 16+ before 18:00, no 18+ before 21:00, and animation brought into the family
film block. Applied to `movies.yml` and `movies-hu.yml`.

**This relaxes the earlier blanket rule, on these two channels only.** The standing rule was
nothing 12 or over before 18:00 everywhere. The Movies channels now permit up to 14 in the
daytime. Recorded explicitly because it is a loosening of a child-safety rule and should not
be discovered later by reading a query: Main, Main HU, Kids and Kids HU are unchanged and
still stop at the under-12 line.

The reason the request is a good one: under the under-12 rule only 37 of 778 films qualified,
about 66 hours against a nine-hour daytime block, so the daytime cycled weekly and the Movies
HU daytime matched **four films**. Raising the ceiling to 14 takes the pool to 299.

    before 18:00   nothing 16+    ceiling hu/14, PG-13    47 + 299 films
    18:00-21:00    nothing 18+    ceiling hu/16          169 + 125 films
    21:00 onward   unrestricted                          417 + 255 + 59 films

Evening blocks shifted an hour later as a consequence — prime drama and action now start at
21:00 rather than 20:00, because they are the unrestricted blocks and 136 hu/18 and 39 R-rated
films live there. **Do not add a ceiling to those three sources**; they are the only home that
material has on the channel.

**Animation was never excluded by genre — it was excluded by rating.** `FAMILY_FILMS` has no
genre filter, so the real blocker was the under-12 cap. Worth noting for future queries that
animation lives in the *Movies* library, not the Animated one: 24 animated films are in Movies
and only 2 in Animated, so `genre:animation` across both libraries is what reaches them. The
daytime is now split 09:00–14:00 animation and family, 14:00–18:00 all genres bar horror.
Horror is held back from the afternoon even when lightly rated.

**`scripts/check_watershed.py` rewritten as an age-ladder checker.** It previously hardcoded
one rule — nothing 12+ before 18:00 — which the new tiers would have failed. It now maps every
content rating in the library to an age, declares each channel's ladder in a `POLICY` table at
the top, and judges each content source against the ceiling in force at the earliest time it
can be reached. Unknown ratings still fail closed below a ceiling, and are ignored above an
unrestricted one. Verdict: **every content source is within the age ceiling for its slot**, and
**0 orphaned shows**.

**Films still unreachable: 14, and 12 of them correctly so** — the `minutes:[60 TO 400]` floor
catching shorts and junk, plus the known 0-minute Star Wars Episode VI stub. The two real ones
are **The Lion King and Spies in Disguise, both tagged hu/18 in Plex**, which is wrong for both.
At 18 they are above the daytime ceiling, and the unrestricted 21:00 blocks are genre-scoped to
drama, thriller, crime, action, adventure, horror and mystery, so animated films cannot land
there either. The right fix is correcting the two ratings in Plex, not widening a query to
accommodate bad metadata. Toy Story 3 and Mufasa, both hu/12, are now reachable.

**Files touched:** `ersatztv/movies.yml`, `ersatztv/movies-hu.yml`,
`scripts/check_watershed.py`, `docs/logs/changes-tracker.md`.

## 2026-10-03 — One four-step age ladder across all channels

Replaces the per-channel rating rules with a single ladder, applied to `main.yml`,
`main-hu.yml`, `movies.yml` and `movies-hu.yml`:

    06:00-14:00   nothing 12+
    14:00-18:00   nothing 16+
    18:00-21:00   nothing 18+
    21:00-06:00   anything

**Block boundaries were moved onto the ladder steps.** The Main afternoon mix now starts at
14:00 rather than 15:00. A single `pad_until` draws from one content source with one rating
ceiling, so a block straddling a step would have to be filtered to the stricter of the two and
the looser half of the window would be wasted.

What changed in each pool: Main's afternoon mix gained TV-14 (888 to 1483 episodes, bringing
in Gilmore Girls, HIMYM, Two and a Half Men, Ally McBeal, Miami Vice); the 20:00 feature film
gained an under-18 ceiling since it begins before 21:00 (735 to 532 films); the Movies daytime
went back to under-12 for 09:00-14:00 (37 films) with the under-16 pool of 299 taking
14:00-18:00. Because US TV ratings jump straight from TV-14 to TV-MA, the 18:00 step changes
nothing for episodes — it only matters to films, where hu/16 becomes available.

**The two children's channels were deliberately left off the ladder** and hold the under-12
ceiling all day. Nothing forces that; it is recorded in `POLICY` in the checker so it can be
undone by deleting two lines.

**I caused a regression and then fixed it, again by capping without rehoming.** Capping the
Movies channel's 18:00 comedy block at under-18 stranded **36 adult comedies over an hour
long** — Blazing Saddles, Tootsie, Poor Things, Me Myself & Irene, War Dogs, the stand-up
specials. Every 21:00+ source was genre-scoped to drama, action, horror or mystery, so comedy
had no unrestricted home anywhere in the repo. This is the third time the same mistake has
appeared: **a rating ceiling on a block is only safe if the excluded material has an
unrestricted block to fall into.**

Fixed by adding two sources to both Movies channels and reworking the 21:00 run to five films:
prime drama, action, `LATE_COMEDY` (242 films, unrestricted), `LATE_GENRE`, then `LATE_ANY`.

**`LATE_ANY` is a deliberate backstop, not a content choice.** Both film libraries, no genre
requirement, no rating ceiling, 779 films, filling the small hours. It is what guarantees no
film in the library is unschedulable — anything with a missing genre, an unrecognised rating
or broken metadata reaches a channel here and nowhere else. It must not gain a genre filter.

**`scripts/check_watershed.py` reworked again.** `DEFAULT_POLICY` now holds the four-step
ladder; the ceiling lookup takes the clock modulo a day so overnight blocks are judged
correctly; and `count` instructions now advance the clock by the *shortest* runtime their
source can match instead of not advancing at all. That last change is what lets the 20:00
feature film legitimately push the block after it past 21:00 — the checker reports NIGHT_TV at
21:19 — while staying conservative, since real playout can only ever run longer.

**Verified:** all six schedules parse, every source referenced and none unused, every source
within its ceiling, **0 orphaned shows and 0 orphaned films over an hour**. The 11 remaining
unreachable films are all under 60 minutes and excluded on purpose by the runtime floor.

**Unknown metadata, which was the question that prompted this.** Unknown *audio language* is
harmless: it only excludes a file from the three HU channels, and the English channels have no
language filter. Unknown *content rating* was the real trap — under an allow-list design an
unrated title can only ever reach an unrestricted block, so before `LATE_ANY` existed, 7
unrated films over an hour (A tizedes meg a többiek, Easy Skanking, Home, Riverdance, the
Jeff Dunham special) aired nowhere while 27 others survived only because they happened to
carry a drama or action genre. `LATE_ANY` closes that class of hole permanently.

No Tom & Jerry *films* exist in the Sep 25 audit snapshot — only the Cartoons shorts — so they
were added since and cannot be verified here. Under the current design they will air if rated:
G/hu/KN/hu/6 puts them in the Movies 09:00 block and the Kids feature, hu/12 in the Movies
14:00 block, and unrated reaches `LATE_ANY` overnight only.

**Files touched:** `ersatztv/main.yml`, `ersatztv/main-hu.yml`, `ersatztv/movies.yml`,
`ersatztv/movies-hu.yml`, `scripts/check_watershed.py`, `docs/logs/changes-tracker.md`.

## 2026-10-04 — Audit re-run against the live library; a whole library was unreachable

Re-ran `scripts/plex_library_audit.py` (read-only GETs) and diffed against the Sep 25 snapshot.
The library has grown from 786 to 884 films and 3604 to 3892 inventory rows. Four findings, two
of them things no amount of careful YAML reading would have caught.

**1. A new `Documentaries` library, 44 titles, referenced by zero queries.** The National
Geographic collection had never aired. This is the answer to the earlier question about why
documentaries were not filling the daytime — they were never in the TV Series library at all.
Two properties made it invisible rather than merely thin: Plex types the library as **movies**,
and `type:movie` cannot share a content source with `type:episode`, so it could not join
`DAYTIME_MIX`; and 37 of the 44 run under an hour, so the `minutes:[60 TO 400]` floor on every
film source would have excluded almost all of them anyway.

Added `DAYTIME_DOCS` to both Main schedules with a 20-minute floor, and split the 10:00–14:00
window so documentaries take 12:00–14:00. **This source trusts library curation rather than
ratings and is a deliberate exception to the allow-list rule** — 30 of 44 titles carry no
rating and 7 more say "Not Rated", so an allow-list would have cut a 44-title library to five.
The two excluded titles are both Plex mismatches rather than real documentaries: "Grand Canyon"
(R, tagged crime|drama) and "Jerusalem" (PG-13, drama). Same reasoning already applied to the
Cartoons library.

**2. Archer has been moved into the Cartoons library.** The morning block's query was
`library_name:"Cartoons" NOT show_content_rating:"TV-MA"` — an exclusion, which this repo
otherwise forbids, justified at the time by the library being curated. That justification no
longer holds: the Cartoons library now contains 75 episodes of TV-MA adult animation, and the
only thing keeping it out of the 06:00 children's block is one rating field. If it were ever
cleared, Archer would air at six in the morning on four channels.

Switched all six cartoon queries (main, main-hu, kids, kids-hu, including both SHORT_CARTOONS)
to an allow-list with two named exemptions:

    (show_content_rating:"TV-G" OR "TV-Y" OR "TV-Y7" OR "TV-PG"
     OR show_title:"Me & Winnie the Pooh" OR show_title:"The New Adventures of Jonny Quest")

The two exemptions are the unrated shows that genuinely belong there. Same 425 episodes as
before, but it now fails closed: a cleared rating removes a show from the morning rather than
adding one. The exemptions are by title, so renaming either show in Plex silently drops it —
which is the safe direction.

**3. Top Gear is tagged `reality|talk show`, not `documentary`.** I had told the user it sat in
the documentary mix on the strength of their report that a documentary query returned it; Plex
says otherwise, so ErsatzTV's index and Plex disagree, or the query differed. Either way the
daytime mix would not have reached it. Added `show_genre:reality` to `DAYTIME_MIX`, which
brings all 172 TV-PG episodes into the 10:00–12:00 block and takes that pool from 1009 to 1235.

**4. The user's two rating fixes are confirmed.** The Lion King and Spies in Disguise no longer
appear as orphans.

**Verified against the fresh data:** all six schedules parse, every source referenced and none
unused, every source within its age ceiling, 11 orphaned films of which 9 are under 60 minutes
and excluded on purpose.

**Three shows still reach no block, all needing a decision rather than a query change:**
Archer (75 ep, TV-MA, now in Cartoons — no non-cartoon query touches that library, so moving it
there removed it from the schedule entirely); House of Cards US (13 ep, unrated and carrying
**no genre at all**, so no genre query can see it); Fabulous Beasts (2 ep, unrated,
animation|short).

**Files touched:** `ersatztv/main.yml`, `ersatztv/main-hu.yml`, `ersatztv/kids.yml`,
`ersatztv/kids-hu.yml`, `ersatztv/audit/library-audit.txt`,
`ersatztv/audit/library-inventory.csv`, `docs/logs/changes-tracker.md`.

Decisions taken on the three unreachable shows:

* **Archer** gets a dedicated `ADULT_ANIMATION` source and a 22:30–23:00 slot on `main.yml`.
  The query is the deliberate mirror of the morning cartoon block — same library, TV-MA only —
  so the two together partition the Cartoons library with no overlap and no gap. Not added to
  `main-hu.yml`: a Hungarian filter on 75 episodes risks an empty block and dead air, and an
  unfiltered one would break that channel's one promise.
* **House of Cards US and Fabulous Beasts** left alone; to be fixed in Plex, where the missing
  genre is the actual defect. Nothing in this repo can reach a show with no genre.
* **Main HU's documentary block stays language-unfiltered**, now recorded as a settled decision
  rather than a thing to verify, on the same grounds as the family shows in `kids-hu.yml`.

Final state: **2 orphaned shows (15 episodes), both awaiting Plex metadata; 0 orphaned films
over 20 minutes.**

## 2026-10-04 (later) — Audit re-run: metadata improved, library did not grow

Re-ran the audit expecting significant growth. There is none: **887 films against 884 this
morning, and TV episodes unchanged at 2616.** Three items total — two documentaries and one
film. If files have been added to disk, Plex has not indexed them, so nothing downstream can
see them. ErsatzTV reads Plex, and this audit reads Plex, so both are blind until a Plex scan
completes.

What *did* change is metadata, and usefully:

* **House of Cards US -> House of Cards**, now rated TV-MA with genres `drama|thriller`. It had
  been unrated and carrying no genre at all, which is why no query could reach it. All 13
  episodes are now schedulable. This was the show flagged this morning as needing a Plex-side
  fix, and the fix worked exactly as predicted.
* **Fantasia 2000: Introduction by Roy Edward Disney -> Fantasia 2000**, now rated G.
* Five Hungarian-titled documentaries rematched to English titles (A Csodás Emberi Test ->
  National Geographic: The Incredible Human Machine, Szigetek Kuba -> Islands Cuba, and so on).
  Worth noting against the earlier decision to leave the Main HU documentary block
  language-unfiltered: the Hungarian titles were the evidence for likely Hungarian narration,
  and rematching has removed that evidence without adding any audio language tags. The decision
  still stands on its own terms, but the reasoning behind it is now weaker.
* `Fr Di S B Ni Leal Z a Fut L Z 1981 Web DL Robzombi -> The Flintstones: Jogging Fever`, which
  has created a **new cross-library duplicate** — that title now exists in both Movies and
  Animated.

**One orphaned show left: Fabulous Beasts** (2 episodes, unrated, `animation|short`). Every
other show in the library now reaches a block. 9 unreachable films remain, all under 60 minutes
bar the two deliberately excluded documentary mismatches.

## 2026-10-04 — Unrestricted step moved to 22:00; the evening became one mixed block

Requested: an under-18 feature around 20:00, the rest of the evening a mix of evening TV and
adult animation, and 18+ only after 22:00. The last clause moves a ladder step, so it changed
all four general channels, not just Main.

    06:00-14:00   nothing 12+
    14:00-18:00   nothing 16+
    18:00-22:00   nothing 18+      <- was 18:00-21:00
    22:00-06:00   anything         <- was 21:00

On the Movies channels the whole unrestricted run shifted an hour later: short films now
realign to 22:00, and prime drama, action, late comedy, late genre and the catch-all follow
from there. Nothing else about that channel changed.

**Main's evening is now one mixed source instead of three blocks.** `NIGHT_TV` and
`ADULT_ANIMATION` were folded into a single `NIGHT_MIX` (2553 episodes) spanning two
libraries — the broad TV Series genre list with the ceiling removed, OR the Cartoons library
restricted to TV-MA. Both halves are `type:episode`, which is what lets them share one query
and shuffle together; the midday documentaries could not do this because Plex types that
library as movies. The Cartoons half is the exact mirror of the morning cartoon query, so the
two together partition that library with no overlap and no gap.

Mixing is proportional, so **Archer is about 3% of the pool** — roughly one episode every
couple of nights, against the guaranteed half hour it had under the dedicated 22:30 slot. Noted
in the file, with the instruction to give it back its own `pad_until` rather than widening the
source if that is too rare.

`show_genre:animation` on the TV Series half also sweeps up **Fabulous Beasts**, the last
orphaned show. **0 orphaned shows and 0 orphaned films over an hour now.**

**The evening floats, and that is worth understanding before judging the schedule.** The 20:00
feature pool runs 78 to 263 minutes, median 117, so the film ends between 21:18 and after
midnight. Measured against the old structure: the film ended by 22:30 on 87% of nights, between
22:30 and 23:00 on 9%, and after 23:00 on 4%. That is why the previous arrangement gave the
unrestricted TV pool about 33 minutes on a median night — it was a remainder, not a block.
Anchoring it to a fixed 22:00-00:00 window fixes that: two hours every night, regardless of
film length, except on the minority of nights when a long film eats into it.

The small gap between the film ending and 22:00 is filled from `EVENING_MIX` with
**`trim: false`** — deliberately, because on a median night that gap is three minutes and
trimming would put a three-minute fragment of a sitcom on screen. Overrunning slightly into
22:00 is harmless at the under-18 ceiling.

Late films moved from 23:00 to 00:00 as a consequence, giving the night mix its two hours.

**Files touched:** `ersatztv/main.yml`, `ersatztv/main-hu.yml`, `ersatztv/movies.yml`,
`ersatztv/movies-hu.yml`, `scripts/check_watershed.py`, `docs/logs/changes-tracker.md`.

## 2026-10-04 — Documentaries and Top Gear mixed across 10:00-18:00

Removed the dedicated 12:00-14:00 documentary block. `DAYTIME_DOCS` is gone and the
Documentaries library now sits inside both daytime mixes, so documentaries can land anywhere
between 10:00 and 18:00. `DAYTIME_MIX` is back to one 10:00-14:00 block.

**This is the only query in the repo that spans two media types, and it needs verifying in
ErsatzTV.** The Documentaries library is typed as MOVIES by Plex while everything else in these
blocks is episodes, so the query is `((type:episode AND ...) OR (type:movie AND
library_name:"Documentaries" AND ...))`. I previously stated flatly that the two types cannot
share a content source; that was an assumption, not a verified fact. `type` is a searchable
field in ErsatzTV so OR-ing across it should work, but it has only been checked against this
repo's own evaluator. The check is to paste the query into the ErsatzTV search box: ~1279 means
it works, ~1235 means the documentary branch is being silently ignored and the library needs its
own block back. Noted in the file at the query itself.

**The cost of mixing, measured.** 44 documentary films against 1235 episodes; weighted by
runtime that is 5.4% of the block, so about **26 minutes a day across 10:00-18:00 against the
120 minutes a day the dedicated block gave them**. A given film returns roughly every 2 days
and the library cycles in about 95 days. Recorded because it sits awkwardly against the earlier
expectation that documentaries would "fill the daytime" — proportional mixing and a guaranteed
block are mutually exclusive, and this was the explicit choice between them.

**Top Gear and The Grand Tour.** Both were asked about. Top Gear is 226 episodes (up from 172
this morning), TV-PG, tagged `reality|talk show` — not documentary, so `show_genre:reality` is
load bearing in both daytime mixes. The Grand Tour is 25 episodes, TV-14, `adventure|reality`,
and was reaching only the evening and night blocks. Adding the same genre set to
`AFTERNOON_MIX` plus the TV-14 ceiling brings it into 14:00-18:00. So Top Gear now reaches
10:00-18:00 and the evening; The Grand Tour reaches 14:00 onwards and never the morning, which
is the rating ladder working as intended rather than a gap.

`AFTERNOON_MIX` is now simply `DAYTIME_MIX` with TV-14 added — the two blocks differ only by
rating ceiling, which is what the ladder is for. 1899 items against 1279.

**Verified:** all six schedules parse, sources all referenced, every source within its ceiling,
**0 orphaned shows**, 10 unreachable films all under an hour. The only Documentaries titles that
reach nothing are Grand Canyon (R) and Jerusalem (PG-13), both excluded on purpose as Plex
mismatches.

**Files touched:** `ersatztv/main.yml`, `ersatztv/main-hu.yml`, `docs/logs/changes-tracker.md`.

## 2026-10-04 — English subtitles: the cause was untagged sidecar files

Reported that the English channels still show no subtitles, with the useful detail that Plex
lists only "a Hungarian and an unknown" subtitle for the file in question. That detail is the
diagnosis.

**ErsatzTV tags a sidecar subtitle `und` when the filename carries no language code**, and Plex
displays the same thing as "unknown". So a folder containing `Film.srt` produces a subtitle that
`subtitle_language: ["en*"]` can never match. The item fails, the ladder falls through to
`disable_subtitles: true`, and nothing appears — even though the subtitle plainly exists and
both Plex and ErsatzTV can see it. The selector was working exactly as written; the metadata
was the problem, which is the third time in this project that an untagged stream has been the
real cause.

Also worth stating plainly, because it shapes what "working" looks like: **ErsatzTV burns
subtitles into the picture and never delivers them as a track.** With MPEG-TS to Plex there
will never be a subtitle menu on the client. "The channel doesn't offer subtitles" is expected;
the thing to look for is burned-in text.

`stream-selector-en.yml` rewritten from six items to nine — each audio tier now gets a
tagged-English attempt, then an untagged-sidecar attempt, then a no-subtitle twin:

    subtitle_condition: "external and lang = 'und'"

**This is a heuristic with a stated failure mode**, documented in the file: it assumes an
untagged sidecar is the English one. True when a file has a tagged Hungarian subtitle plus one
unknown, which is the common shape here. Wrong for a file whose only sidecar is an untagged
Hungarian subtitle, which will burn Hungarian text onto an English channel.

**The real fix is renaming the files** — `Film.srt` to `Film.en.srt`, then a Plex rescan and an
ErsatzTV Deep Scan. ErsatzTV accepts the code before or after a forced/sdh marker
(`Film.en.forced.srt` and `Film.forced.en.srt` both work). Once tagged, items 2, 5 and 8 can be
deleted and the guesswork disappears.

Two global settings also recorded in the file: `Use embedded subtitles` (default on) and
`Extract and use embedded (text) subtitles` (default **off**, because extraction is slow).
Sidecar files do not need extraction, but embedded text subtitles are ignored entirely until
the second is enabled, and custom stream selectors specifically skip embedded text subtitles
that have not been extracted.

The diagnostic for all of this is **Support -> Troubleshooting -> Playback**, which takes a
Stream Selector option and reports which stream was chosen along with its real `lang` value.
That is how to confirm whether an untagged sidecar actually arrives as `und`.

**Files touched:** `ersatztv/stream-selector-en.yml`, `docs/logs/changes-tracker.md`.

## 2026-10-04 — Trimming end credits: not possible in YAML, viable via scripted schedules

Research only, no files changed. Asked whether ErsatzTV can cut off part of the end credits,
given that Plex knows where they are.

**ErsatzTV cannot do this in a sequential schedule, and does not read Plex markers at all.**
Checked the full playout instruction reference and the upstream changelog. `count` takes only
`content`, `custom_title` and `filler_kind` — there is no in-point, out-point, or per-item
duration. The only trimming that exists is "trim to fit a time boundary" (`trim: true` on
`duration`, `pad_until`, `pad_to_next`), which cuts at a wall-clock moment rather than at a
point measured from the item's own end, so it cannot target credits. ErsatzTV does have
chapter support (mid-roll filler between chapters, `Use Chapters As Media Items` on filler
presets, external Matroska Chapter XML files, `chapters` in the search index), but chapters
only influence what gets *inserted*, never which part of the item plays.

**The scripted-schedule path does work.** Fetched the OpenAPI description from the running
instance (`/openapi/scripted-schedule.json`) and confirmed the two primitives needed:

* `add_search` takes `key`, `query`, `order` — so a script can define a content source
  containing exactly one film at build time.
* `add_duration` takes `duration` and `trim` — so that one film can be cut to an exact length.

So the design is: pick the film in script, look up its credits marker in Plex, build a
one-film source with `add_search`, then `add_duration` with
`duration = credits_start + grace` and `trim: true`. Because that duration is shorter than the
film, the item never "fits", trim fires, and the cut lands exactly where intended.

One primitive is NOT usable for this: `peek_next` returns only `{content, milliseconds}` — the
source key and a runtime. **It does not identify the item**, so a script cannot ask ErsatzTV
what is playing next and then look it up in Plex. The script has to choose the film itself,
which is why `add_search` is load-bearing.

**Measured the payoff across the library** (851 films of 60 min or more, markers pulled from
Plex via `includeMarkers=1`):

| | |
|---|---|
| with a credits marker | 781 |
| no credits marker | 70 |
| more than one marker (mid/post-credits scenes) | 114 |

Credits tail, measured as runtime minus the first credits marker: median 5.5 min, p75 7.2,
p90 9.2, max 54.7. With a 2-minute grace the reclaimed time is a median of **3.5 min per
film** — 221 films save 5+ minutes, only **15 save 10 or more**, and 94 save nothing.

So the "20 minutes of credits" intuition is mostly wrong: the distribution is tight around five
minutes with a thin tail. The tail is where the value is. `Get Smart` reports a 160-minute
runtime with credits starting at 105 (a 55-minute tail), which almost certainly means that file
has extras appended — worth a look independently of this feature. The three Lord of the Rings
films sit at 20-27 minutes each.

**Costs if built,** recorded so the trade is visible later: the channel moves from declarative
YAML to Python, which means `scripts/check_watershed.py` can no longer verify its age ladder;
the container needs a new volume mount at `/app/scripted-schedules/scripts`; and the script
needs a Plex token at runtime inside the container. The 114 films with multiple markers need
care — cutting at the first marker would discard mid- and post-credits scenes.

## 2026-10-04 — Hungarian subtitles burned over Hungarian audio, and a polluted HU channel

Reported watching a film on the Hungarian channel, in Hungarian, with Hungarian subtitles
burned in. Traced to two separate faults. The first is fixed; the second is measured but
needs one check in the UI before it can be fixed.

### Fault 1 — the wildcard item in the Hungarian stream selector

Identified the exact film by querying the running instance: `/api/sessions` showed one viewer
on channel 6, and the XMLTV guide had `Wrongfully Accused` airing 18:17-19:39 on Filmek. Plex
reports that file (`Sziki-szökevény_hun.avi`) as:

* one audio track, `Unknown (MP3 Stereo)` — **no language tag at all**
* an external `en` SRT (SDH) and an external `hu` SRT

The filename says `_hun` and the viewer confirms the audio is a Hungarian dub. In
`stream-selector-hu.yml`, items 1 to 3 all require a `hu` or `en` audio tag, which an untagged
track cannot match, so it fell through to item 4 — `audio_language: ["*"]` paired with
`subtitle_language: ["hu*"]` — and the Hungarian subtitle was burned over the Hungarian dub.

**A wildcard cannot distinguish a third language from an untagged stream.** Item 4 was written
for "some third language, give it Hungarian subtitles" but silently also caught every untagged
file. 175 of 919 films have no audio language tag; 118 of those carry a Hungarian subtitle.

Fixed by converting item 4 into an allow-list of real language tags, measured from the library
rather than guessed (fr 52, it 39, es 39, de 24, cs 19, ru 15, pl 14, pt 10, ja 9, th 4, tr 4,
da 2, sv 2, hi 2, ar 1, zh 1, sk 1, plus common European tags and `zxx` for the silent films).
Untagged audio now falls to the catch-all and plays **no** subtitles. This is the same
allow-list-never-exclusion principle already used for content ratings, and it fails in the
right direction: an untagged file that reached a Hungarian channel is more likely a dub than
not, and no subtitles beats the wrong ones. The old item 5 became redundant and was dropped,
so the file went from 5 items to 5 with different roles.

Five of the 28 films in the current Filmek guide were in the broken state: Eyes Wide Shut,
Fantasia 2000, French Kiss, Top Gun: Maverick, Wrongfully Accused.

### Fault 2 — `language_tag:hu*` appears to match Hungarian SUBTITLES, not just audio

Every content source in `movies-hu.yml` ends with `AND language_tag:hu*`, and the file's own
header asserts this restricts the channel to "films that carry a Hungarian audio track".
**That premise looks wrong.** Cross-referencing the published guide against Plex's stream data
for the 28 films currently scheduled on Filmek:

| audio on Filmek's scheduled films | count |
|---|---|
| Hungarian audio track present | 12 |
| English-tagged audio only, no Hungarian track | 11 |
| no audio language tag at all | 5 |

So **16 of 28 films on the Hungarian movie channel have no Hungarian audio**. Since all six
sources carry the language filter, the only way those films can have been selected is if
`language_tag` matches subtitle language tags too. The reasoning rules out the alternative: if
ErsatzTV's own probe had found a `hu` audio tag that Plex missed, selector item 1 would have
matched and subtitles would have been disabled — which is not what happened.

Supporting evidence from the upstream changelog: `language_tag` was added early, and
`sub_language` / `sub_language_tag` were added *later* as separate fields, which is consistent
with `language_tag` covering all streams.

Not fixed, because the fix depends on whether an audio-only search field exists, and the docs
site has no search-field reference page. `NOT sub_language_tag:hu*` is not the answer — it
would exclude genuine dubs that also ship a Hungarian subtitle, which is the common case.

**One check settles it:** type `title:"Top Gun: Maverick" AND language_tag:hu*` into ErsatzTV's
search box. If it returns the film, `language_tag` includes subtitles and all three HU channels
are scheduling subtitle-only matches.

### Also learned

* The complete custom stream selector reference: `audio_language`, `audio_title_blocklist`,
  `audio_title_allowlist`, `audio_condition` (fields `id`, `title`, `lang`, `default`,
  `forced`, `codec`, `channels`), `disable_subtitles`, `subtitle_language`,
  `subtitle_title_blocklist`, `subtitle_title_allowlist`, `subtitle_condition` (same fields
  plus `sdh` and `external`), and `content_condition` (`channel_number`, `channel_name`,
  `time_of_day_seconds`).
* ErsatzTV is on `26.8.0-docker-amd64`, API version 3.
* Useful read-only endpoints on the running instance: `/api/version`, `/api/channels`,
  `/api/sessions` (who is watching what right now), `/iptv/channels.m3u`, `/iptv/xmltv.xml`,
  `/openapi/v1.json`, `/openapi/scripted-schedule.json`.

**Files touched:** `ersatztv/stream-selector-hu.yml`, `docs/logs/changes-tracker.md`.

## 2026-10-07 — Clipped programmes at every boundary, and embedded subtitles being ignored

Reported turning on live TV at 23:56, seeing the guide promise Die Hard at midnight, then
watching a 21-minute episode start anyway and vanish — with Die Hard confirmed playing by
00:09. Also no subtitles on that episode despite it having English ones. Two unrelated causes.

### Fault 1 — `trim: true` guaranteed a clipped programme at every daypart boundary

The guide was correct and the Apple TV was not lagging. XMLTV shows Die Hard at exactly
00:00-02:12, so the episode that started at 23:56 was **cut dead after four minutes**, which
was the viewer's own second guess.

`pad_until: "00:00"` on NIGHT_MIX had `trim: true`, which takes the next item and cuts it to
end exactly on the boundary. **`discard_attempts` was already set to 3, but it only applies
when `trim` is false** — with trim on, ErsatzTV never looks for an item that fits. So the
header comment in `main.yml` claiming "discard_attempts first tries to find something that
fits" was simply wrong, and no value of that number could have helped. Every boundary on the
channel was producing a fragment: five per day on Main.

Fixed on `main.yml` and `main-hu.yml`. All seven `pad_until` instructions now use
`trim: false`, `discard_attempts: 12`, and `fallback: "FILLER"`. The boundary still lands
exactly on the clock and nothing overruns, because `stop_before_end` defaults to true and an
item is scheduled only if it fits whole.

New content source on both files:

    FILLER   type:episode AND library_name:"Cartoons" AND minutes:[1 TO 9]
             AND (show_content_rating:"TV-G" OR "TV-Y" OR "TV-Y7" OR "TV-PG")

271 items, 3 to 9 minutes, median 7 — Tom and Jerry (159) and Dexter's Laboratory (112). It
reuses the rating allow-list from the morning CARTOONS block, so Archer cannot reach it.
**Being under-12 throughout is the property that lets one source serve all seven boundaries
including 06:00**, and `scripts/check_watershed.py` confirms it: FILLER is evaluated at its
earliest slot of 06:00 against the `<=10` ceiling and passes. Full run still reports
"every content source is within the age ceiling for its earliest slot".

The 06:00 boundary deserves its own note: it is the only one where the ladder *tightens*
rather than loosens, so letting content overrun there would put an unrestricted late film in
the children's block. `stop_before_end: true` is what prevents that, and it must stay.

Side effect worth stating: a cartoon short will now appear in gaps of a few minutes, including
late at night before a film. That is deliberate — a clipped Tom and Jerry is a far smaller
intrusion than a drama cut mid-scene.

### Fault 2 — ErsatzTV silently ignores embedded text subtitles

Sampled 400 episodes and classified their English subtitle streams:

| | |
|---|---|
| external SRT (works) | 247 |
| **embedded text, ignored** | **71** |
| embedded image / PGS (works) | 6 |
| no English subtitle at all | 76 |

So **about one episode in five that has English subtitles cannot show them**, including Grey's
Anatomy, Californication, Pan Am, Archer, Top Gear, Planet Earth II and The Mandalorian. Codec
breakdown of those streams: 111 embedded `srt`, 9 `mov_text`, 6 `ass`.

The cause is the global setting **`Extract and use embedded (text) subtitles`, which defaults
to OFF** because extraction adds overhead — and the changelog is explicit that a custom stream
selector will "ignore embedded text subtitles that have not been extracted". External SRT and
image-based PGS need no extraction, which is why Die Hard had subtitles and the episode did
not. Nothing in `stream-selector-en.yml` can fix this; the subtitle is invisible to the
selector until extraction is enabled. **Action for the user: ErsatzTV Settings, turn that on.**

### Not addressed

`kids.yml`, `kids-hu.yml`, `movies.yml` and `movies-hu.yml` were left alone and still have the
old boundary behaviour. `movies.yml` is mostly `trim: false` already but has no `fallback`, and
the kids channels use `trim: true`. They need the same treatment.

**Files touched:** `ersatztv/main.yml`, `ersatztv/main-hu.yml`, `docs/logs/changes-tracker.md`.

## 2026-10-07 — Hungarian audio on an English channel, missing and desynced subtitles, no interstitials

Four problems reported from an hour of actually watching channels 2 and 3. None of the earlier
fixes were deployed yet, so all of this was observed against the original configuration.

### 1. 7th Heaven played in Hungarian on the English Kids&Family channel — FIXED

Plex's stream data explains it completely. Those files carry **no audio language tags at all**.
The multi-language version has three audio tracks that are merely *titled*, in Hungarian:
`magyar`, `angol`, `francia`. Several episodes also exist as two separate versions — one
single-track file and one three-track file.

With nothing to match, the selector's English items failed, the Hungarian items failed too
(there is no `hu` tag either), and the wildcard catch-all took the first available track, which
is the dub. The English subtitles the viewer saw came from that same wildcard item, which pairs
any audio with `en` subtitles. So "Hungarian audio with English subtitles" was not a random
fault — it was the documented fallback chain working exactly as written on a file that gives it
nothing to work with.

Fixed using `audio_title_allowlist`, which discards audio streams whose title contains none of
the listed strings. `stream-selector-en.yml` gained two items (now 11) matching
`["angol", "english", "eng"]`, placed above the Hungarian items so a named English track wins.
`stream-selector-hu.yml` gained one item (now 6) matching `["magyar", "hungarian", "hun"]`,
placed above the *English* items so that on a Hungarian channel a named dub beats a tagged
English track.

**Swept all 3111 episodes in TV Series and Cartoons to size this honestly:**

| | |
|---|---|
| English audio tagged (selector already worked) | 1392 |
| **no tag and no title clue anywhere** | **1464** |
| only a Hungarian-titled track | 74 |
| no English tag but a track titled English | 19 (all 7th Heaven) |
| episodes with more than one version | 686 |

So the fix repairs the reported show and nothing else. **1464 episodes — 47% — give ErsatzTV no
machine-readable way to know which track is English.** No stream selector can fix those; this
is the audio-tagging debt that has now caused four separate visible faults. `mkvpropedit` sets
a track language in place without re-encoding and remains the highest-leverage work available.

The 686 multi-version episodes are a second, separate hazard: ErsatzTV picks one version and we
cannot see or influence which, so even a correct selector can be handed the wrong file.

### 2. Georgie & Mandy had no subtitles — CONFIRMED, needs a settings change

Its English subtitle is an **embedded** SRT titled `English [SDH]`; only the Hungarian one is
external. Embedded text subtitles are invisible to a custom stream selector until
`Extract and use embedded (text) subtitles` is enabled in Settings, which it is not. Version
26.6.0 specifically added "extract embedded text subtitles (when enabled in settings) on
channels that use custom stream selectors", so on 26.8.0 this will work once switched on.
Same root cause as the 2026-10-07 entry above; this is the second confirmed instance.

### 3. English subtitles "totally out of sync" on two unrelated channels — NOT DIAGNOSED

Deliberately not guessed at. There are two plausible causes and they need different fixes:

* **The subtitle files simply do not match the video.** 7th Heaven is a strong candidate: two
  different video releases share one external SRT, and old AVI DVDRips mix 25 fps PAL with
  23.976 fps NTSC, which drifts progressively rather than sitting at a constant offset.
* **ErsatzTV mishandling seek.** Both observations were made after tuning in mid-programme,
  when ErsatzTV seeks into the file. Historic changelog entries show this class of bug ("fix
  playback with text subtitles when seeking into content, i.e. when first joining a channel",
  25.x; "fix seeking into extracted text subtitles"), all fixed well before 26.8.0 — but the
  symptom matches.

**Two tests separate them.** Play the same episode directly in Plex with the same subtitle: if
it is out of sync there too, the file is at fault and ErsatzTV is innocent. Then use
Support -> Troubleshooting -> Playback, which has a **`Seek Seconds`** field added specifically
"to support capturing timing-related issues": compare 0 against 600 on the same title. In sync
at 0 and out of sync at 600 means the bug is ErsatzTV's seek handling.

### 4. No separation between programmes — a title card is ready to test

Built `ersatztv/graphics/now-playing.yml`, a text graphics element that fades a lower-third in
for roughly the first fifteen seconds of every programme:

    opacity_expression: "LinearFadeDuration(content_seconds, 1, 1, 12)"

`content_seconds` counts from the start of the item and the expression is evaluated per item,
so a single `graphics_on` at the top of a playout yields a card at every transition rather than
one card per day. Joining mid-programme shows nothing, which is right — the card marks a
transition and there was none.

**Deliberately not wired into any schedule.** Graphics elements deploy to a *third* location,
`/opt/ersatztv/config/templates/graphics-elements/text/`, and two fields in it
(`opacity_expression` and the `MediaItem_*` variables) come from the changelog rather than a
documented example. Support -> Troubleshooting -> Playback can select graphics elements and
render them immediately, so it gets verified there before touching a live channel.

### 5. Unrelated but urgent: a security fix is available

The instance reports `26.8.0-docker-amd64`. **26.8.1 fixes GHSA-h3r4-r2f2-qf59 (CVE pending)**
and states that "all users who link Plex or Emby media servers should upgrade as soon as
possible", recommending the Plex token be rotated afterwards via Media Sources -> Plex ->
Re-authenticate with Plex. It also fixes a case where crafted requests could reach the
management UI over the streaming port.

Note for this repo's own tooling: 26.8.1 makes `X-Etv-Api-Key` **required** on all `/api`
requests, so the read-only `/api/channels` and `/api/sessions` calls used for diagnosis will
stop working after the upgrade. The key is generated at startup in `api-secrets.json` in the
config folder. `/iptv/*` and `/openapi/*` are unaffected.

**Files touched:** `ersatztv/stream-selector-en.yml`, `ersatztv/stream-selector-hu.yml`,
`ersatztv/graphics/now-playing.yml` (new), `docs/logs/changes-tracker.md`.

## 2026-10-07 — "All the files have their subtitles off-sync" is substantially a file problem

Follow-up to the report that every file's subtitles look desynced. "All files" ruled out the
per-title SRT-mismatch theory I had offered for 7th Heaven, so it needed measuring rather than
more guessing.

### The measurement

Plex serves subtitle streams over HTTP (`/library/streams/{id}`), so each external subtitle can
be fetched and its final cue compared against the video's real runtime. **A subtitle whose last
cue falls after the end of the video cannot be correct**, and there are no false positives:
there is no legitimate reason for dialogue to be timed past the closing frame.

| external English subtitles sampled | 152 |
|---|---|
| **subtitle ends past the end of the video** | **42 (28%)** |
| of those, stretched like a PAL/NTSC mismatch | 25 |

Concentrated in exactly the shows that air most: Friends 13, How I Met Your Mother 6,
7th Heaven 6, Ally McBeal 6, TaleSpin 5, Two and a Half Men 2.

Two distinct failure modes, and they need different fixes:

* **PAL/NTSC stretch** — ratios clustering at 1.042 to 1.057, which is 25 fps against
  23.976 fps. The error *grows* through the episode rather than sitting still: about 54 seconds
  by the end of a 21-minute sitcom. Mechanically repairable by multiplying every timestamp by
  23.976/25 = 0.95904.
* **A different cut entirely** — Friends at 1.18 and TaleSpin at 1.11, where a subtitle for a
  21-minute episode ends at 25 minutes. Rescaling cannot fix these; they need replacing.

### New tool

`scripts/subtitle_sync_audit.py`, read-only, following the conventions of
`plex_library_audit.py` (token from `~/.plex_token`, `--url`, `--out-dir`). Writes
`ersatztv/audit/subtitle-sync-<lang>.txt` and a `.csv` worklist carrying the suggested scale
factor per row. Takes `--lang` so the Hungarian subtitles can be audited the same way.

**Its blind spot is stated in its own docstring and matters:** it can only see subtitles that
run too LONG. A constant offset — consistently three seconds early — passes as plausible and is
indistinguishable from a good file without listening to the audio. So 28% is a floor, not an
estimate, which is consistent with the viewer's impression that it affects everything.

### Still unresolved: whether ErsatzTV is also at fault

28% explains a lot but not "all". The decisive test is free and has not been run yet, because
every observation so far was made after tuning in **mid-programme**, which is when ErsatzTV
seeks into the file:

* **Watch a programme from its scheduled start.** In sync there but not when joining late means
  ErsatzTV's seek handling, not the files.
* **Support -> Troubleshooting -> Playback** has a `Seek Seconds` field added specifically "to
  support capturing timing-related issues". Compare 0 against 600 on one title.

Checked for a known bug: the only relevant open item is "Fix text subtitle playback (regression
from `v26.8.1`)" in Unreleased, which does not apply to 26.8.0. Historic seek-and-subtitle bugs
("fix playback with text subtitles when seeking into content, i.e. when first joining a
channel") were all fixed well before this version.

### The cheaper alternative, not applied

Every English item at the top of `stream-selector-en.yml` currently pairs English audio with
English subtitles. Changing item 1 to `disable_subtitles: true` would stop burning
same-language subtitles over audio that is already understood, which removes the most visible
instance of the problem at a stroke and leaves subtitles where they are actually needed — on
Hungarian and other foreign audio. Not applied because subtitles on English audio were an
explicit earlier request.

**Files touched:** `scripts/subtitle_sync_audit.py` (new),
`ersatztv/audit/subtitle-sync-en.txt` and `.csv` (new output), `docs/logs/changes-tracker.md`.

## 2026-10-07 — Same clipping hit again; all six channels now consistent

Reported a series cut short and a new one starting. `/api/sessions` showed the viewer on
channel 4, Főcsatorna, at 18:01 — the **18:00** daypart boundary on `main-hu.yml`, where
AFTERNOON_MIX hands over to EVENING_MIX. Same `trim: true` cause as the midnight incident. The
fix for `main.yml` and `main-hu.yml` was already written but **has not been deployed yet**, so
the live config is still the old one.

The guide was already showing the next two clips before they happened, which is a useful way to
see the problem without waiting for it:

| channel | programme | scheduled | length |
|---|---|---|---|
| Main | 7th Heaven | 19:45-20:00 | 14.9 min |
| Főcsatorna | Northern Exposure | 19:48-20:00 | 11.1 min |

Both are fragments of 44-minute episodes, cut to make room for the 20:00 feature film.

### The kids channels were already right

`kids.yml` and `kids-hu.yml` never had this problem: they omit `trim` entirely, which defaults
to false, and already carried `fallback: "SHORT_CARTOONS"`. That is why every complaint so far
has come from Main, Főcsatorna and the film channels. Only their overnight `pad_until: "07:00"`
lacked a fallback, now named for consistency.

### A quieter fault found on the film channels

`movies.yml` and `movies-hu.yml` use `trim: false` with no `fallback`, and that combination
does **not** clip — it ends the block EARLY and starts the next instruction immediately. Caught
it happening live: the 18:00 block ran out at 17:49 and `Project Hail Mary` (156 min, scheduled
by the `count: 1 COMEDY` instruction) began at 17:49, eleven minutes before the rating step it
belongs to.

**Ending early is a quiet age-ladder leak.** The shortest film in these pools is 60 minutes, so
a block can finish up to an hour early and let the next, looser block begin up to an hour
before its ceiling was meant to rise. It is also what made `scripts/check_watershed.py`
optimistic: the checker assumes each block starts at its stated time, and without a fallback
that assumption is false.

Both film channels now have a `FILLER` source and a fallback on all four `pad_until`
instructions. The 09:00 boundary also moved from `trim: true` to `trim: false` + fallback — it
is the one boundary on those channels where the ladder *tightens*, so nothing may overrun it,
and `stop_before_end` defaulting to true gives that guarantee without cutting a film dead.

### All six channels verified consistent

Every `pad_until` across all six files now has no `trim` and a defined `fallback`, with no
dangling source references. `check_watershed.py` passes, evaluating FILLER against the `<=10`
ceiling at 06:00 on the Main pair and 09:00 on the film pair.

Side effect of closing the leak: because boundaries now land on the clock instead of drifting
early, the checker's model finally matches what actually airs.

**Files touched:** `ersatztv/movies.yml`, `ersatztv/movies-hu.yml`, `ersatztv/kids.yml`,
`ersatztv/kids-hu.yml`, `docs/logs/changes-tracker.md`.

## 2026-10-09 — Prime time is now films on both Main channels

Reported Friends and Top Gear on the Main channels at 21:30, with the first film not until
00:00, and that the slot should be films.

### Two corrections of detail, one confirmed substance

**At 21:30 tonight the guide actually has a film on both channels** — `Mad City` on Main
(20:00-21:54) and `Twister` on Főcsatorna (20:00-21:53). So the 21:30 reading was off; if the
Apple TV showed series there, that is the stale Plex guide, which has not been refreshed since
the playouts were last built.

**The substance was right.** The film ends around 21:54 and the next one is at 00:00, so
roughly two hours of series sat between them: Friends 21:54, Top Gear 22:16, How I Met Your
Mother 23:17, Archer 23:39. That is series occupying prime time.

**The earlier clipping fix is still not deployed.** Confirmed properly this time — my first
check was wrong, because Tom and Jerry and Dexter's Laboratory legitimately appear in the
06:00-10:00 cartoon block, so finding them there proved nothing. The real test is cartoon
shorts appearing *outside* that block, used as boundary filler:

| signature | Main | Főcsatorna |
|---|---|---|
| filler shorts outside the cartoon block | 0 | 0 |
| programmes clipped to end exactly on a boundary | 9/day | 9/day |

Including a 1.1-minute Top Gear and a 0.2-minute Friends. The live config is still the
`trim: true` version.

### The restructure

Both Main files now run three films back to back from 20:00:

    20:00  count 1  FEATURE_FILM   (under-18, starts before 22:00)
    ~21:55 pad      EVENING_MIX    (mops up to exactly 22:00)
    22:00  count 1  NIGHT_FILM     (new, unrestricted)
    ~00:00 count 1  LATE_NIGHT     (horror/thriller/mystery)
    ~02:00 pad      NIGHT_MIX      (series, through to 06:00)

`count: 1` and not `pad_until` for the film slots, deliberately. A film block cannot use a pad:
the gap left after one film is routinely under an hour, nothing in a 60-to-263 minute pool
fits, and the fallback would loop cartoon shorts for forty minutes at 23:20. With `count` each
film plays whole and the next starts when it ends. Only the 22:00 anchor is fixed, held by the
pad above it.

### A fourth instance of the same old bug, found while doing this

The new `NIGHT_FILM` source is `type:movie AND library_name:"Movies" NOT genre:animation AND
minutes:[60 TO 400]` with **no rating cap** — 803 films, of which **228 sit above the under-18
ceiling**.

Those 228 had no home on Main at all. `FEATURE_FILM` is capped at under-18 because it starts at
20:00, and `LATE_NIGHT` is scoped to horror, thriller and mystery, so an adult film outside
those genres could not air on the channel. Same mistake as the adult sitcoms, the 36 adult
comedies and Archer: **a rating ceiling on a block is only safe if the excluded material has an
unrestricted block to fall into.** Fourth occurrence.

### The cost, stated plainly

358 episodes are rated above TV-14 — Californication 84, Archer 75, Game of Thrones 68, Strike
Back 21, Landman 20, House of Cards 13, The Borgias 12, Westworld 11 — and the ladder allows
them only after 22:00. Moving the series block to 02:00-06:00 keeps every one of them on the
channel and in the guide, but they will rarely be watched live. Deleting the block instead of
moving it would have stranded them, so this was the lesser of the two. It is reversible by
swapping the series block back above the two `count` instructions.

`check_watershed.py` passes. Earliest starts: NIGHT_FILM 22:00, LATE_NIGHT 23:03, NIGHT_MIX
00:26 — all in unrestricted territory. On a median night the series block actually begins
around 02:00.

**Files touched:** `ersatztv/main.yml`, `ersatztv/main-hu.yml`, `docs/logs/changes-tracker.md`.

## 2026-10-09 (2) — Main channels: five films a day, and the night block stops being the whole catalogue

Follow-up to the entry above. Three things reported: that adult films belong in NIGHT_FILM on
age alone with no genre filter; that an adult series landing in the evening film block is fine
but Friends and Top Gear there is not; and that too much of the day is daytime series with too
few feature films — with 7th Heaven counted at nine slots in one day.

### What the guide actually showed

Measured from ErsatzTV's own XMLTV for Fri 9 Oct, Main, 11:00-00:00:

| programme | airtime that day | slots |
|---|---|---|
| Top Gear | 251 min | 4 |
| 7th Heaven | 134 min | 5 |
| The Big Bang Theory | 80 min | 4 |
| Friends | 64 min | 4 |
| **films** | **115 min** | **1** (Mad City) |

One film in thirteen hours. The repetition is pool arithmetic, not a shuffle bug: weighted by
runtime, Top Gear is 30.4% of the pre-14:00 pool and 7th Heaven 19.6%, and four shows are 75%
of it. Shuffling cannot make a pool more varied than the pool is. Against 16 daytime-rated
shows the library holds 828 feature films, so films are the only available source of variety.

### Found while measuring: NIGHT_MIX was never "adult series"

`NIGHT_MIX` carried **no rating restriction at all**. That does not mean adult series — it
means *every* series in the library, 2553 episodes, a strict superset of the daytime pool. Top
Gear and The Big Bang Theory alone were 300 of them. That is why Top Gear aired at 22:16 and a
12-second sliver of Friends at 23:59, and it is the direct cause of the complaint.

It is now an allow-list of the 404 episodes that no other block on the channel can reach:
TV-MA 358 (Californication 84, Archer 75, Game of Thrones 68, Strike Back 21, Landman 20,
House of Cards 13, The Borgias 12, Westworld 11, Foundation 10, Treadstone 10, Masters of the
Air 9, Big Little Lies 7, Breaking Bad 7, Dune: Prophecy 6, Chernobyl 5) plus 46 unrated
(Terapia 40, The Fear Index 4, Fabulous Beasts 2).

The three unrated shows are **named explicitly rather than swept in with `NOT`**, because the
unrated set also contains Me & Winnie the Pooh (25) and The New Adventures of Jonny Quest (26).
An exclusion-based query would have put children's cartoons in the 02:00 slot and left these
three unreachable. Naming a show is safe in a way that `NOT rating` never is.

### Two new daytime film blocks

| source | slot | ceiling | films | notes |
|---|---|---|---|---|
| `MATINEE` | 12:00 | cap 10 | 54 | City Lights, 12 Angry Men, Dial M for Murder, American Graffiti |
| `AFTERNOON_FILM` | 16:00 | cap 14 | 320 | hu/12 is 222 of them; median 110 min |

Horror dropped from both; animation kept (13 of the 54). The matinee pool is small, so a film
returns about every two months — but every one is a different film, which is the point.

The new day on Main: cartoons 06:00-10:00, series 10:00-12:00, **film**, series to 16:00,
**film**, series 18:00-20:00, **film**, **film**, **film**, adult series 02:00-06:00. Five
films and about 9.7 hours of film a day, against three films and 6 hours before. Expected
7th Heaven airtime falls from the measured 134 min/day to roughly 44 — about one episode
instead of five — and it is now excluded from `EVENING_MIX` outright, because the 19:44 slot
that prompted this was a daytime family drama in the pre-prime hour.

### NIGHT_FILM is age-only, as asked

`LATE_NIGHT` is deleted. It was scoped to horror, thriller and mystery — 143 films — and that
scoping did damage in two directions: it made the late slot monotonous, and since
`FEATURE_FILM` is capped at under-18, an adult film outside those three genres had no block on
the channel it could reach at all. 228 films were in that position. `NIGHT_FILM` is now
`type:movie AND library_name:"Movies" AND minutes:[60 TO 400]` — 828 films, runtime and library
scope only — and both night slots draw from it.

### The mop-up pads after each film are load bearing

A `count` ends whenever its film ends, so the next instruction inherits an arbitrary clock. The
matinee runs 60-251 minutes, so it can finish at 13:00; letting `AFTERNOON_MIX` follow it
directly would put TV-14 on screen an hour inside the under-12 ceiling. Each film is therefore
followed by a pad drawing from the **same source as the block before it**, holding the stricter
ceiling up to the step. If the film overruns the step instead, the pad is a no-op —
`tomorrow: false` with a time already past schedules nothing, which is the wanted behaviour.

`check_watershed.py` passes on all six schedules. Earliest starts on Main: MATINEE 12:00 cap 10,
AFTERNOON_FILM 16:00 cap 14, FEATURE_FILM 20:00 cap 16, NIGHT_FILM 22:00 unrestricted.

### Needs checking by hand

The checker cannot see `language_tag`, so every Hungarian source reports 0 items. The new
`MATINEE` on `main-hu.yml` is the one at real risk of being empty — the under-12 band is where
the library is thinnest. If it is empty the playout degrades gracefully (the slot is skipped and
the 14:00 pad covers it), but it should be confirmed in ErsatzTV's search box.

**Files touched:** `ersatztv/main.yml`, `ersatztv/main-hu.yml`, `docs/logs/changes-tracker.md`.

## 2026-10-09 (3) — Marathon ordering, and the real cause of the wrong-language audio

Two questions: why 7th Heaven played in Hungarian on the English channel when English versions
exist, and whether a series can advance its episodes sequentially instead of at random.

### `language_tag` is the AUDIO language — I had this wrong before

Settled from the official search-field reference, not inference. For every media type the docs
list four separate fields:

    language          the audio stream language
    language_tag      the audio stream language tag
    sub_language      the subtitle stream language
    sub_language_tag  the subtitle stream language tag

So `language_tag` is audio only. An earlier entry in this log reversed that and claimed it was
matching subtitle tags; that was wrong and the earlier inference was right. The open question
about the Hungarian channels — whether `language_tag:hu*` was selecting films that have no
Hungarian audio — now has a different answer: ErsatzTV runs its own scan, so its index and
Plex's API can disagree. Worth one search in ErsatzTV's own box to confirm.

### The wrong-language audio is a Plex duplicate-version problem

Measured against Plex for 7th Heaven, all 200 episodes:

| version shape | episodes |
|---|---|
| Hungarian release only | 90 |
| Hungarian release first, English rip second | 66 |
| English rip first, Hungarian release second | 38 |
| English rip only | 5 |
| two English rips | 1 |

**Plex's first version — the one ErsatzTV plays — is the Hungarian release for 156 of 200.**
Of the 194 Hungarian-release files only 17 carry an `angol` audio track, so the
`audio_title_allowlist` added to `stream-selector-en.yml` earlier can rescue 17 episodes and no
more. The English rips are real but they are stacked as a *second* Plex version, and ErsatzTV
plays one version per media item. Worked example:

    v1  /mnt/media/TV/7th Heaven/7th Heaven s1e01 - Anything You Want.avi        1 untagged track
    v2  .../Hetedik mennyorszag S01-S11/.../7th.Heaven.S01E01.avi                magyar | angol | francia

This also explains the out-of-sync subtitles on this show. The external English `.srt` belongs
to the NTSC English rip; the Hungarian release is a 25 fps PAL transfer. Playing one against
the other produces exactly the growing 1.0427 drift the subtitle audit measured.

**It is library-wide.** 689 of 3146 episodes have more than one version, 573 of them in
different folders, i.e. two separate releases:

| show | duplicated | of | what the duplicates are |
|---|---|---|---|
| Gilmore Girls | 153 | 153 | `Szívek Szállodája` dual-audio vs an older dual DVD rip |
| Two and a Half Men | 151 | 188 | a subtitle working directory (`1/srt-taahm_s1e01.avi`) got scanned |
| 7th Heaven | 105 | 200 | English rip vs Hungarian release |
| Californication | 72 | 84 | English BluRay vs HUN dual vs a Spanish-subtitled AVI |
| Grey's Anatomy | 52 | 250 | same file twice, once inside a release-named subfolder |
| Dexter's Laboratory | 51 | 127 | **different shorts merged — see below** |

Sampling 14 episodes of each major English-channel show for what audio version 1 actually
offers:

| show | result |
|---|---|
| The Big Bang Theory | 13 English-tagged, 1 untagged |
| Gilmore Girls | 11 English-tagged, **3 Hungarian-tagged** |
| Top Gear | 10 English-tagged, 2 Hungarian, 2 untagged |
| Grey's Anatomy | **7 Hungarian-tagged, 7 English-tagged** |
| Showder Klub | 8 Hungarian-tagged, 6 untagged |
| How I Met Your Mother | 8 with two untagged tracks, 6 with one |
| 7th Heaven, Friends, Ally McBeal, Northern Exposure, How It's Made | every sample a single untagged track |

Half of Grey's Anatomy is dubbed, and a stream selector cannot help: it chooses between streams
*within* an item, so if the item's only audio is Hungarian it falls through and plays Hungarian.
Only a schedule-level `language_tag:en*` filter or correct tagging fixes that — and the filter
would drop every untagged show, which is most of the daytime pool.

### Found while measuring: Dexter's Laboratory is losing shorts

`Dexter's Laboratory - 2x01a - Beard to be Feared` and `2x01c - Ant Pants` are **different
cartoons** that Plex merged into one S02E01 because it parsed `a` and `c` as the same episode.
51 of 127 episodes are affected, so roughly 60 distinct shorts are unreachable — they are
versions of an item ErsatzTV will never choose. This directly shrinks the `FILLER` pool.
Animaniacs has the same problem on 3 episodes.

### Two shows held off the English channel

`NOT show_title:"7th Heaven" NOT show_title:"Showder Klub"` added to `DAYTIME_MIX`,
`AFTERNOON_MIX` and `EVENING_MIX` in `main.yml` only. Showder Klub is Hungarian stand-up with no
English audio to find. Both remain on `main-hu.yml` where they are correct. This is a workaround
for a Plex problem, not a fix, and the clause should be deleted once the duplicate versions are
split apart.

### Marathon content sources — sequential episodes, and equal shares

`order: shuffle` on a `search` source picks from a flat pool, which caused both complaints at
once: episodes came out jumbled (S01E10, S09E11, S02E06, S04E11 in one day), and airtime
followed pool size, so Top Gear's 226 episodes bought it 30.4% of the pre-14:00 block.

Nine sources across four schedules are now `marathon` instead:

```yaml
  - marathon:
    key: "DAYTIME_MIX"
    searches:
      - "type:episode AND library_name:\"TV Series\" ..."
    group_by: "show"
    item_order: "chronological"
    play_all_items: false
    shuffle_groups: true
```

`item_order: chronological` makes each show advance S01E01, S01E02, S01E03 across days.
`play_all_items: false` takes one episode from a show before moving to the next, so **every
show gets an equal share of slots regardless of how many episodes it owns** — Top Gear goes
from 30.4% to roughly 1/14. `shuffle_groups: true` randomises which show is up next.

Converted: `CARTOONS`, `DAYTIME_MIX`, `AFTERNOON_MIX`, `EVENING_MIX`, `NIGHT_MIX` on both Main
channels, and `CARTOONS`, `FAMILY_SHOWS`, `NATURE` on both Kids channels. Film sources stay
`search`/`shuffle` — films have no episode order. `FILLER` and `SHORT_CARTOONS` stay `shuffle`
because they are gap-fillers.

Caveat worth remembering: **a playout reset restarts every show at S01E01.** Right behaviour
here, but the position is not preserved across the resets needed to deploy changes.

### Documentaries moved to their own slot

`group_by: show` is undefined for a film, and `DAYTIME_MIX`/`AFTERNOON_MIX` had the
Documentaries library OR-ed in as `type:movie`. The film branch is now a separate `DOCUMENTARY`
source with `count: 1` at 10:00. Side benefit: as a proportional garnish they were 5.4% of the
block, about 26 minutes a day; they now get one guaranteed programme daily.

### Checker updated

`scripts/check_watershed.py` read `c["query"]`, which a marathon does not have. It now reads
`searches` too and treats a marathon as the union of its searches. Passes on all six schedules.

**Files touched:** `ersatztv/main.yml`, `ersatztv/main-hu.yml`, `ersatztv/kids.yml`,
`ersatztv/kids-hu.yml`, `scripts/check_watershed.py`, `docs/logs/changes-tracker.md`.

## 2026-10-09 (4) — Why `show_title:"7th Heaven" AND language_tag:en*` returns nothing

Searches run in ErsatzTV: 1314 episodes match `language_tag:en*`, 1418 do not, and 7th Heaven
matches zero — despite Plex showing an English audio track.

### `angol` is a stream TITLE, not a language tag

The supplied XML for S01E01 settles it. Across both versions there are four audio streams and
**not one carries a `languageTag` or `languageCode` attribute**:

    v1 (English rip)        Stream 42033  streamType=2  mp3   no title, no language
    v2 (Hungarian release)  Stream 55778  streamType=2  mp3   title="magyar"   no language
                            Stream 55779  streamType=2  mp3   title="angol"    no language
                            Stream 55780  streamType=2  mp3   title="francia"  no language
                            Stream 61518  streamType=3  srt   languageTag="en" languageCode="eng"

Plex says so itself: every one of those audio streams has `displayTitle="Unknown (MP3 Stereo)"`.
The `angol` text lives in `extendedDisplayTitle`, because it is free-text typed by whoever made
the release. A language tag is ISO 639 metadata in the container; a title is a label. ErsatzTV's
`language_tag` field indexes the former, which does not exist here, so the search is correctly
empty.

Note the one stream that *does* carry `languageTag="en"` is the **subtitle**. That is why
ErsatzTV has a separate `sub_language_tag` field, and it is the detail that caused the earlier
confusion in this log about what `language_tag` matches.

Consequence for the stream selector: `audio_title_allowlist: ['angol', ...]` is the only thing
that can reach this audio, which is why it was added — but it only works on version 2, and
only 17 of 194 Hungarian-release files have an `angol` track.

### Per-show English audio tagging, measured

Cross-checked against Plex's own `audioLanguage` filter, which agrees with ErsatzTV: 1289
English-tagged of 2623 TV Series episodes (ErsatzTV says 1314 — the gap is version handling).
538 are Hungarian-tagged.

| show | eps | en-tagged | hu-tagged | status |
|---|---|---|---|---|
| The Big Bang Theory | 280 | 242 | 0 | 86% tagged |
| Grey's Anatomy | 250 | 178 | 94 | **71% — the rest dubbed** |
| Friends | 232 | 0 | 0 | no tags at all |
| Top Gear | 226 | 168 | 43 | 74% tagged |
| 7th Heaven | 200 | 0 | 0 | no tags at all |
| Two and a Half Men | 188 | 32 | 16 | 17% tagged |
| Gilmore Girls | 153 | 109 | 153 | 71% tagged |
| Miami Vice | 115 | 115 | 0 | fully tagged |
| How I Met Your Mother | 112 | 0 | 0 | no tags at all |
| Northern Exposure | 110 | 0 | 0 | no tags at all |
| How It's Made | 104 | 0 | 0 | no tags at all |
| Ally McBeal | 88 | 0 | 0 | no tags at all |
| Terapia | 40 | 0 | 24 | Hungarian only |
| Showder Klub | 21 | 0 | 13 | Hungarian only |
| Breaking Bad | 7 | 0 | 5 | Hungarian only |

### Decision: do NOT add `language_tag:en*` to the English channel

It would be correct and it would gut the channel. Friends, 7th Heaven, How I Met Your Mother,
Northern Exposure, How It's Made and Ally McBeal — 846 episodes — carry no tags at all and would
all disappear, taking the daytime marathon from 6 shows to 3. Untagged does not mean wrong
language; it means unknown, and for language (unlike age ratings) failing open is acceptable
because the downside is a dubbed episode rather than a child seeing the wrong thing.

What was done instead is targeted: **Terapia (40) and Breaking Bad (7) removed from the English
`NIGHT_MIX`**, since both are measurably Hungarian-only. Terapia was one of the three unrated
shows named into that allow-list yesterday; it is the Hungarian *In Treatment*, so the Hungarian
channel is where it belonged all along. NIGHT_MIX drops from 404 to 357 episodes.

The real fix remains tagging: `ffmpeg -i in.avi -map 0 -c copy -metadata:s:a:0 language=eng`
is lossless and fast, and 846 untagged episodes of otherwise-English shows are the highest-value
batch.

### Marathon round-robin has a flip side, found while verifying

Equal shares per group fixes Top Gear hogging 30% of the morning. It also means a show with one
episode gets the same share as one with 280. Measured on the first cut of the new `DAYTIME_MIX`:
Planet Earth I, II and III were 3 of 9 groups — 33% of daytime series slots — off 25 episodes
total, and `National Geographic Explorer` would have aired its single episode more often than any
episode of Friends.

Fixed by moving the small documentary series into the `DOCUMENTARY` slot, where shuffle across 84
items means a given one returns about every three months. `How It's Made` is named back into the
series marathon, because 104 episodes round-robin fine. Group counts now:

| source | groups | share each | smallest group |
|---|---|---|---|
| CARTOONS | 7 | 14.3% | Animaniacs 3 |
| DAYTIME_MIX | 6 | 16.7% | Georgie & Mandy 22 |
| AFTERNOON_MIX | 14 | 7.1% | The Jeff Dunham Show 1 |
| EVENING_MIX | 20 | 5.0% | The Jeff Dunham Show 1 |
| NIGHT_MIX | 16 | 6.2% | Fabulous Beasts 2 |

Three tiny groups remain because they have nowhere else to go, and repeating them was judged
better than stranding them. Documented in the schedules so the trade is visible.

`check_watershed.py` passes on all six schedules.

**Files touched:** `ersatztv/main.yml`, `ersatztv/main-hu.yml`, `ersatztv/kids.yml`,
`ersatztv/kids-hu.yml`, `docs/logs/changes-tracker.md`.

## 2026-10-09 (5) — Slot-by-slot audit of the rewritten schedules

Asked for a bigger table of what sits in each time slot, to catch wrong content in wrong
places. Built by evaluating every content source against the inventory CSV and walking each
playout the way `check_watershed.py` does, so each time shown is the earliest that source can be
reached. Rendered as a canvas: `canvases/ersatztv-slot-audit.canvas.tsx`.

36 slots measured across the five channels whose sources are not language-filtered. **Zero
age-ceiling breaches** by the machine check — and that turned out to be the point worth making,
because reading the pools found things the check structurally cannot see.

### The age ladder is only as good as Plex's ratings

Three adult films are rated child-safe in Plex and therefore sit in both children's film pools —
`MATINEE` (Main, 12:00) and `FAMILY_FILMS` (Movies, 09:00–14:00):

| film | Plex rating | what it is |
|---|---|---|
| Taken (2008) | **hu/6** | Liam Neeson abduction-and-torture thriller |
| The Odessa File (1974) | PG | Nazi-hunter thriller |
| The Hill (1965) | **hu/KN** (suitable for all) | brutal military prison drama |

`check_watershed.py` passes these because it reads the same rating Plex gives it. No schedule
change can catch this class of fault; the ratings have to be corrected in Plex. Borderline cases
also present: `She's Out of Control` (a 1989 comedy about sexualising a teenage daughter),
`Dial M for Murder`, `12 Angry Men`.

### A 251-minute matinee destroys the rest of the day

`MATINEE` has no runtime ceiling beyond the 400-minute library guard. `Cleopatra` (251 min)
starting at 12:00 runs to 16:11 and swallows the 16:00 afternoon film whole; `Lawrence of Arabia`
(227 min) ends at 15:47. Capping the source at `minutes:[60 TO 150]` drops 5 of 54 films and
makes the slot predictable. Not applied — it is a taste call.

### NIGHT_FILM lost its floor along with its ceiling

Making it age-only, as asked, means 374 of its 828 films are under-16 material. `Mufasa: The
Lion King`, `Toy Story` and `My Fair Lady` can air at 22:00 and 23:00. Not a safety issue, but it
reads as a scheduling error. Needs either a genre floor or a rating floor, or accepting it.

### Duplicates are inflating the children's pools

`KIDS_MOVIES` reports 22 films but holds 19 distinct ones. `Fantasia` (G and hu/6), `Pooh's Grand
Adventure` (G twice) and `The Many Adventures of Winnie the Pooh` (G and hu/KN) are each counted
twice, so they are twice as likely to be drawn. These are the cross-library Animated↔Movies
duplicates already on the outstanding list; this quantifies the cost.

### Kids 15:00–18:00 is two shows

`FAMILY_SHOWS` has exactly two groups: 7th Heaven (200 episodes) and Georgie & Mandy (22). With
marathon round-robin they alternate, so Georgie & Mandy covers half of three hours a day off 22
episodes and recycles in under a fortnight.

### Metadata noise now visible in the guide

* `TEKNO3D.com - Rogue One: A Star Wars Story 4K VISIONPLUSHDR-1000 Chroma ...` is the title of a
  film in the `ACTION` pool and will appear verbatim in the Plex guide.
* `Michael Jackson's Thriller` is listed at 98 minutes from `MJ-PrisM.avi`. The video is 14
  minutes, so this is a compilation under the wrong title — and wrong runtimes propagate into
  every pad decision.
* `Friends S07E708` has a bad episode number. Harmless to playback, but `item_order:
  chronological` sorts on it, so it lands at the end of season 7 in the rotation.

**Files touched:** `canvases/ersatztv-slot-audit.canvas.tsx` (new),
`docs/logs/changes-tracker.md`.

## 2026-10-09 (6) — Matinee runtime ceiling

Response to the slot audit: the 251-minute matinee should go, but the long musicals are the
point of a matinee and should stay.

`MATINEE` on both Main channels is now `minutes:[60 TO 185]`. 185 rather than 150 deliberately —
it keeps `Fiddler on the Roof` (181) and `My Fair Lady` (173), and the worst case now ends at
15:01 with the 16:00 afternoon film intact. Excluded: `Cleopatra` (251) and `Lawrence of Arabia`
(227), which starting at 12:00 ran to 16:11 and 15:47 and made the afternoon film unreachable.
Pool goes from 54 films to 52.

`Hello Dolly` is not in the library — the only match for "Dolly" is `Berry and Dolly -Playmates`.

`NIGHT_FILM` keeps no rating floor, confirmed as wanted: `My Fair Lady` in the evening is fine.

### Friends season 7: the numbering is harmless, the titles are not

| season | episode numbers | generic `Episode N` titles |
|---|---|---|
| 1-5, 9, 10 | 1-n | 0 |
| 6 | 1-25 | 2 |
| **7** | **701-724** | **24 of 24** |
| 8 | 1-24 | 1 |

The odd numbering does **not** break `item_order: chronological`. The season number is correctly
7, and 701 through 724 sort ascending, so season 7 still falls between 6 and 8 and plays in
broadcast order inside itself. Marathon grouping is by show, so only the (season, episode) sort
matters and it is correct.

The real fault is that all 24 episodes carry no title — Plex never matched them, which is also
why the numbers are raw. The guide will read "Friends — Episode 708". Fixing the filenames to
`S07E08` form and re-matching in Plex repairs the titles and the numbering together. Three more
episodes elsewhere in the show have the same problem (2 in season 6, 1 in season 8).

**Files touched:** `ersatztv/main.yml`, `ersatztv/main-hu.yml`, `docs/logs/changes-tracker.md`.

## 2026-10-09 (7) — The afternoon gets `drama`, and the nature series come back to it

The proposed 15:00–18:00 line-up turned out to be a near-exact description of Main's existing
`AFTERNOON_MIX`, which made the two things it was *missing* the useful finding.

**`show_genre:drama` added to `AFTERNOON_MIX`.** The genre list was family / comedy / reality
only, so `Grey's Anatomy` (250 episodes, `drama|romance`) and `Pan Am` (14, `drama|history`)
could not reach this channel at any hour before 18:00 even though both sit well inside the
14:00 ceiling. This is a smaller cousin of the strand bug: not a rating ceiling with no
fallback, but a genre list narrower than the block it gates. It also admits `Miami Vice` (115,
TV-14) and `The Pillars of the Earth` (8, TV-14), both reasonable here.

**`show_genre:documentary` added and the five nature-series exclusions dropped**, so Planet
Earth I/II/III, MegaStructures, Ancient Megastructures, Amazing Planet, Ultimate Factories and
National Geographic Explorer air in the afternoon as well as in the 10:00 documentary slot.
Chosen in full knowledge of the cost below.

Pool: **14 shows / 1594 episodes → 26 shows / 2021 episodes.** Nothing in it exceeds age 14, so
the ceiling holds by construction rather than by exclusion, and `check_watershed.py` still
reports no breach. `DAYTIME_MIX` (cap 10) and `EVENING_MIX` are unchanged — Grey's Anatomy is
TV-14 and so is correctly confined to 14:00 onward.

### The flip side, recorded because it is the predictable complaint

`play_all_items: false` with `group_by: show` gives each show one slot per cycle regardless of
episode count, so a show's share is now 1/26 = 3.8% rather than 1/14 = 7.1%. At roughly 8 slots
in the block a full cycle takes about three days. `National Geographic Explorer` has **one**
episode, so that episode airs every three days, exactly as often as any single episode of
Grey's Anatomy. `Amazing Planet` (3) and `Ultimate Factories` (2) are nearly as thin. If this
grates, the fix is to name those three out of the afternoon and leave them in the 10:00
documentary slot, which is where they were an hour ago.

**Files touched:** `ersatztv/main.yml`, `ersatztv/main-hu.yml`, `docs/logs/changes-tracker.md`.
Still not deployed — `Reset All Playouts` required when it is, since content sources changed.

## 2026-10-09 (8) — The morning gets documentaries, and the ladder explained

Prompted by a good question: why does TV-PG Northern Exposure play at 11:00 while TV-14 Gilmore
Girls waits until the afternoon? Because **TV-PG is milder than TV-14**, not harsher. The
checker scores TV-Y and TV-G at 0, TV-Y7 at 7, TV-PG and plain `PG` at 10, TV-14 at 14, TV-MA
and `R` at 17. Northern Exposure clears the morning ceiling of 10; Gilmore Girls does not clear
anything before the 14:00 step. No change needed, and Northern Exposure stays in the morning.

### The real finding: the morning had the same genre gap as the afternoon

`DAYTIME_MIX` was **six shows** — Big Bang, Friends, Top Gear, Northern Exposure, How It's Made,
Georgie & Mandy. `documentary` and `drama` are now added, matching the change made to
`AFTERNOON_MIX` an hour earlier, so it is **15 shows / 1028 episodes**. The nine newcomers are
Planet Earth I/II/III, MegaStructures, Ancient Megastructures, Amazing Planet, Ultimate
Factories, National Geographic Explorer and Pan Am. Every one of them was inside the age
ceiling already and barred purely by genre. `show_title:"How It's Made"` was dropped from the
query because `show_genre:documentary` now covers it; the show is still in the pool.

The price, recorded because it is the predictable complaint: those nine shows carry **54
episodes between them** and take 9 of 15 slots per round-robin cycle. Share per show falls from
16.7% to 6.7%, so National Geographic Explorer's single episode now airs about as often as any
one episode of The Big Bang Theory, in the morning and again in the afternoon.

### DOCUMENTARY is now the 44 films only, and keeps its slot

The 40 documentary episodes have a better home, so this source holds just the Documentaries
library. It could not be merged away entirely, for two measured reasons:

- **It cannot join the marathon.** `group_by` accepts only show, season, artist and album, and a
  movie has none of those, so a `type:movie` search inside a marathon is undefined behaviour. If
  each film became its own group it would claim 44 of 59 morning slots.
- **It cannot join MATINEE.** These films are 23–96 minutes with a median of 52 — they are
  45-minute TV documentaries misfiled as movies, not features. Folding them into the midday film
  would make 45% of "matinee films" a 45-minute documentary, against the whole point of the
  earlier rewrite.

So one slot remains, straight after the cartoons at 10:00.

### Open inconsistency: 7th Heaven on the English Kids channel

7th Heaven is named out of `main.yml` because Plex's primary version is the Hungarian release
for 156 of 200 episodes. It is **not** named out of `kids.yml`, where it reaches `FAMILY_SHOWS`
via `show_genre:family` — so the English Kids channel still airs it dubbed, 15:00–18:00. The
exclusion was not applied there because `FAMILY_SHOWS` is only two shows and removing 7th Heaven
leaves Georgie & Mandy's 22 episodes to fill three hours a day. Needs a decision, not a
unilateral fix.

**Files touched:** `ersatztv/main.yml`, `ersatztv/main-hu.yml`, `docs/logs/changes-tracker.md`.

## 2026-10-09 (9) — 7th Heaven: the rescue is real but small, and the wrong version was deleted

Two new pieces of evidence changed this diagnosis: an ErsatzTV debug log, and a re-measurement
of Plex after the duplicate versions were removed.

### The debug log proves the title-based rescue works

ErsatzTV reports the untagged tracks as `{"Language":"und","Title":"magyar"}`,
`{"Language":"und","Title":"angol"}`, `{"Language":"und","Title":"francia"}`. The stream title
IS visible to the selector, so `audio_title_allowlist: ["angol", "english", "eng"]` can isolate
the English track despite there being no `languageTag`. My earlier claim that the track was
unreachable was wrong on the mechanism.

The same log also shows every running selector item with `"AudioTitleAllowlist":[]`, which
confirms the deployed selector is the old nine-item version. The fix has been sitting in
`ersatztv/stream-selector-en.yml` undeployed.

### But it only reaches 19 episodes, because the English files are gone

Plex at 15:10, 194 files, one version each, all from the same Hungarian release pack:

| audio tracks | files | where |
|---|---|---|
| one untagged, untitled mp3 stereo | 174 | seasons 2–11 |
| magyar + angol + francia | 17 | season 1 |
| magyar + english | 2 | S10E14, S10E22 |
| magyar + Commentary + francia | 1 | S01E15 |

So 19 episodes have an identifiable English track. The other 174 have exactly one track, so no
selector can change what plays.

### The deletion went the wrong way

This morning the show had 200 episodes, with an English rip stacked as a second Plex version on
110 of them. ErsatzTV plays one version per item — Plex's first — and that was the Hungarian
release for 156 of 200. The fix was therefore to delete the **Hungarian** version, not the
English one, which would have left ErsatzTV with nothing but the English rip to play.

Deleting the English versions instead removed the only English audio for roughly 104 episodes
and took 6 episodes out of the library entirely (200 → 194). The quality judgement was correct
in isolation; a lower-quality English rip is still the only way to air the show in English.
Worth checking whether the files are still on disk or in Plex's trash.

### Season gaps, pre-existing

51 of 245 broadcast episodes absent. Season 7 is missing entirely (no folder — it cannot have
been part of today's deletion, since 194 + 6 = 200 and season 7 is 22 episodes). Season 11 has
1 of 23. Also missing: S01E03/04/12/20, S02E12/15, S06E23.

### Unverified

Whether the 174 single-track files are Hungarian. Metadata cannot say: no `languageTag`, no
`languageCode`, title empty. Inference is Hungarian — they come from a pack whose season 1
files list `magyar` first — and it matches the reported symptom. Confirm by ear in
Troubleshooting → Playback on S02E01. If English, the `main.yml` exclusion can be deleted.

**Files touched:** `ersatztv/main.yml` (language note re-measured),
`docs/logs/changes-tracker.md`.

## 2026-10-09 (10) — The 19 English-capable 7th Heaven episodes are scheduled again

The selector was always going to pick the `angol` track; it had simply never been deployed. So
the remaining work was on the schedule side: let those episodes, and only those, back onto the
English channel.

### Scoped by season and episode number, no file changes

`DAYTIME_MIX` and `AFTERNOON_MIX` in `main.yml` now carry a **second search**. A marathon is the
union of its searches and `group_by: show` keeps them as one group, so the show earns one slot
per round-robin cycle rather than the nine airings in a day that started this thread.

```
type:episode AND show_title:"7th Heaven" AND ((season_number:1 AND NOT episode_number:15)
  OR (season_number:10 AND (episode_number:14 OR episode_number:22)))
```

`season_number` and `episode_number` are documented episode search fields, so nothing on disk
had to change. S01E15 is excluded by number: its second track is titled `Commentary`, not
`angol`, so the allowlist would miss it and it would fall through to selector item 7 and air
dubbed. Live count 19; the checker reports 23 because `library-inventory.csv` predates today's
deletion and still lists S01E03/04/12/20.

Pools: `DAYTIME_MIX` 1028 → 1051, `AFTERNOON_MIX` 2021 → 2044. Watershed check still clean —
7th Heaven is TV-PG, age 10, valid in both blocks.

### `validate_ersatztv_queries.py` gained the two fields

`fields()` did not expose `season_number` or `episode_number`, and `match_term` returns False
for an unknown field name. The rescue clause would therefore have evaluated to False and the
checker would have silently under-counted instead of erroring. Both are now populated from the
inventory's existing `season` and `episode` columns.

### Verified against the official docs

- `audio_title_allowlist` is the correct key, and the "Prefer RiffTrax" sample in
  https://ersatztv.org/docs/advanced/custom-stream-selector pairs it with `audio_language` in
  exactly the shape used here. Ours uses `audio_language: ["*"]` rather than `["en*"]` because
  the tracks report as `und`.
- "Audio and subtitle criteria must both be matched in a single item to finalize stream
  selection" — confirms why the file needs a no-subtitle twin for every audio tier.

### Known cosmetic consequence

The matched item is `audio_title_allowlist` + `subtitle_language: ["en*"]`, and S01's sidecar is
`English SDH` (`hearingImpaired="1"`). So these episodes will play English audio with
hearing-impaired English subtitles burned in. Consistent with this file's stated design
("English subtitles forced on wherever they exist") but probably not wanted over English audio.
Moving the `disable_subtitles: true` twin above its subtitled sibling fixes it in one line.

**Files touched:** `ersatztv/main.yml`, `scripts/validate_ersatztv_queries.py`,
`docs/logs/changes-tracker.md`. `ersatztv/stream-selector-en.yml` unchanged — already correct,
still undeployed.

## 2026-10-10 — Stale inventory found, Terapia excluded, and a count I cannot reconcile

Triggered by a spot-check of the Hungarian matinee returning 12 titles in ErsatzTV's search box.

### `library-inventory.csv` was stale, so the watershed check was not trustworthy

Regenerated from Plex. **+146 items, −27 removed, and `content_rating` changed on 78 items** —
yesterday's Plex rating fixes plus today's version deletions had never been pulled in. Notable:

| item | was | now |
|---|---|---|
| Terapia | *unrated* | TV-PG |
| Showder Klub | TV-PG | TV-MA |
| The Fear Index | *unrated* | TV-MA |
| Taken | hu/6 | hu/18 |
| 12 Angry Men, The Hill, Dial M for Murder, The Odessa File, She's Out of Control | PG / hu/KN | hu/16 |
| The Lion King | hu/14 | hu/18 |

The audit fixes all landed. `Showder Klub` moving to TV-MA also silently closed a hole: at TV-PG
with genre `comedy` it had been inside `main-hu.yml`'s under-10 morning pool.

The check still reports no breach, but it was being run against data that predated the fixes it
was supposed to verify. **Regenerating the inventory belongs before every watershed run**, not
occasionally.

### Terapia reached the 10:00 morning block, and no rule could have stopped it

Forty episodes of adult psychotherapy drama, in the cap-10 block on both Main channels. Two
changes that were each harmless alone combined: Plex gave it a rating (unrated → TV-PG), and
`show_genre:drama` was added to `DAYTIME_MIX` and `AFTERNOON_MIX` the day before. TV-PG scores
age 10, so `check_watershed.py` passes it and always would.

Now named out of both blocks on both Main files. `main-hu.yml` still reaches it via the
explicit `NIGHT_MIX` clause; on `main.yml` it is now unreachable, which is correct for a
Hungarian-language show. Pools: DAYTIME_MIX 1088 → 1048, AFTERNOON_MIX 2081 → 2041.

This is the third time a wrong Plex rating has beaten the machine check (`Taken` hu/6,
`The Odessa File` PG, now Terapia TV-PG). The pattern: **a rating ceiling cannot protect
against a rating that is wrong.** Only a name can.

Two more that are inside the ladder but are judgement calls, left alone: `The Pillars of the
Earth` (TV-14, 8 eps) and `The Jeff Dunham Show` (TV-14, 1 ep), both now in the afternoon.

### Unresolved: ErsatzTV says 12, Plex says 25

For `main-hu.yml`'s MATINEE. Measured against Plex directly: 25 films carry Hungarian audio,
an under-10 rating, a 60–185 minute runtime and no horror genre. Two hypotheses tested and
both rejected:

- *Films lack a `languageTag` so ErsatzTV cannot index them* — no: all 25 have a `hu` tag.
- *ErsatzTV indexes only the default audio stream* — no: 24 of 25 have Hungarian as default.

So the gap is unexplained. Pending a bisection in ErsatzTV's own search box, expected counts
from Plex being 404 → 392 → 25 → 25 as the clauses are added. A stale ErsatzTV index is the
remaining candidate, though staleness should inflate the count rather than shrink it.

**Files touched:** `ersatztv/main.yml`, `ersatztv/main-hu.yml`,
`ersatztv/audit/library-inventory.csv`, `ersatztv/audit/library-audit.txt`,
`docs/logs/changes-tracker.md`.

## 2026-10-10 (2) — The English channel's real problem: 1269 episodes with no audio tag

### Ally McBeal is not a selector failure

`ally.mcbeal.s01.e01.avi` has **exactly one audio track**: mp3 stereo, `languageTag=None`,
`languageCode=None`, `title=None`, which Plex renders "Unknown (MP3 Stereo)". There is nothing
for a selector to choose between — the catch-all item plays the only track, and by ear that
track is a Hungarian dub. Across a 40-episode sample, 23 episodes have one untagged track and
17 have two untagged tracks; in the dual case neither tag nor title distinguishes them, so even
`audio_title_allowlist` is useless and only `audio_condition` on stream index could reach them.

### The systemic measurement

For every show in `main.yml`'s three mix pools, counted via Plex's `audioLanguage` filter:

| | episodes |
|---|---|
| in the English TV pool | 2293 |
| **carrying no audio language tag at all** | **1269** |

Fully untagged shows: Friends 232, 7th Heaven 194, How I Met Your Mother 112, Ally McBeal 111,
Northern Exposure 110, How It's Made 104, Planet Earth 11, Ancient Megastructures 5, Amazing
Planet 3. Partially: Two and a Half Men 140 of 188, Big Bang 38 of 280, Top Gear 15 of 226.

Correctly tagged and safe: Miami Vice, The Grand Tour, The Mandalorian, Pan Am, Coupling, Halo,
Moon Knight, Georgie & Mandy, Planet Earth II/III, The Pillars of the Earth, Joey.

Caveat on the arithmetic: a dual-audio episode is counted by both the `eng` and `hun` filters,
so for shows like Gilmore Girls and Joey the untagged column goes negative. Those are
dual-audio, not miscounted.

**This supersedes an earlier assumption in this project that untagged audio meant English.**
Ally McBeal disproves it. The language of the other 1269 is genuinely unknown — Plex cannot say,
ErsatzTV cannot say, and no stream selector can act on it. It needs an ear, then `ffmpeg
-metadata:s:a:N language=...` to make it permanent.

### Top Gear subtitles: the file is not the fault

- The SRT's first cue really is at `00:00:00,000` ("Tonight, / James drives a Rolls-Royce"), so
  a subtitle appearing immediately is correct, not a symptom.
- 1029 cues, last ending 59:53.2 against a 60.5 minute video. Ratio **1.0104** — nowhere near
  the 1.0427 of a 25fps-vs-23.976fps mistiming, and the 37-second tail is consistent with
  closing credits.
- Channel ffmpeg profile has `normalizeFramerate: false`, so framerate conversion is not
  scaling the timeline. `deinterlaceVideo: true` is on against a progressive mpeg4 source,
  which is wasteful but should not shift timestamps.

So neither the SRT nor the profile explains it, and the remaining question is whether the error
is constant or growing — which decides between shifting and rescaling. Needs one observation of
the error early and late in the same episode.

**Files touched:** `docs/logs/changes-tracker.md` only. No schedule changes.

## 2026-10-10 (3) — The deploy silently did nothing, and now it cannot

### What actually happened

All six schedules on disk differ from the repo, and `grep -c season_number
/config/sequential-schedules/main.yml` returns **0** — so the deployed `main.yml` predates the
7th Heaven rescue entirely.

| file | on disk | repo |
|---|---|---|
| main.yml | `f98f1b78…` | `33e77d2b…` |
| main-hu.yml | `407aeb6f…` | `63a4b6a7…` |
| kids.yml | `2cc18112…` | `0ce07ddc…` |
| kids-hu.yml | `73742e8d…` | `25db2634…` |
| movies.yml | `05b2fcaa…` | `51237b80…` |
| movies-hu.yml | `b7604b50…` | `0c8de3fc…` |

The `scp` step transferred nothing, so the follow-up `sudo install` copied whatever stale
copies were already in `/tmp`. ErsatzTV then did exactly the right thing: it rebuilt its
playouts from the files it had.

**Everything downstream was a phantom.** The schedule that "would not take", the two channels
whose playouts "refused to reset", the 7th Heaven restriction with no effect — all one cause.
The earlier reasoning that channels 1 and 3 had failed builds while 2/4/5/6 succeeded was
wrong: all six rebuilt from stale files, and 1 and 3 simply happened to reshuffle to the same
result. `ls /config/*.yml` also confirms there are no stale duplicates in the config root, so
that theory is dead too.

### `scripts/deploy_ersatztv.sh`

New. Copies the six schedules and two selectors, then compares md5 sums **as seen from inside
the container** and exits non-zero on any mismatch, printing "Do NOT reset playouts". Takes the
host as an argument or `ETV_HOST` so no address is baked in. Stages to a clean
`/tmp/etv-deploy` rather than `/tmp`, so a stale file cannot be picked up again. Also removes
the stray stream-selector copies from the schedules folder.

It deliberately does **not** reset playouts or refresh the Plex guide — both are visible to
anyone watching — but it prints both steps on success.

The lesson worth keeping: a deploy that cannot fail loudly will eventually fail quietly.

### Top Gear S10E03: one bad subtitle file, not a system fault

`ffprobe` on the source: `format.start_time`, video `start_time` and audio `start_time` are all
`0.000000`, duration 3630.68s. There is no container offset for ErsatzTV to misread, so its
rendering the first cue at frame zero is correct — the SRT says zero.

And the SRT is the anomaly. Across Top Gear season 10, first-cue times are 1.0s, 1.0s, 1.0s,
10.6s, 12.3s, 15.6s, 16.4s, 21.2s, 21.2s — and **S10E03 alone at 00:00:00,000**. One
individually mis-timed subtitle file, which fits Big Bang, Ally McBeal and a movie all burning
in correctly. It needs a positive shift on that one file; `scripts/subtitle_sync_audit.py`
handles ratio errors, not head shifts, so this is a manual one-off.

**Files touched:** `scripts/deploy_ersatztv.sh` (new), `docs/logs/changes-tracker.md`.

## 2026-10-11 — `deploy_ersatztv.sh`: one password prompt, and verification that works

Two faults in yesterday's first cut, both found on first real use.

**Four password prompts.** Each step opened its own SSH connection. The script now opens a
single multiplexed connection (`ControlMaster=auto` with a `mktemp`-generated `ControlPath` and
`ControlPersist=180`), reuses it for every step including the file transfer, and tears it down
via an `EXIT` trap with `ssh -O exit`. One prompt for the whole run. It deliberately does not
touch any SSH credential files — key-based auth is the operator's call, not a deploy script's.

**The verification step could never have worked.** It ran `sudo docker exec ersatztv md5sum …`
with the output captured in a subshell, so `sudo` had no terminal to prompt on and the whole
thing died with "a terminal is required to read the password". The missing `-t` was not the
right fix either, because a PTY injects carriage returns into the output being parsed.

Verification now reads the host paths **without privilege**. The files are installed mode 644
and the host directory is bind-mounted straight into the container as `/config`, so an
unprivileged read is equivalent to asking the container. If the read comes back empty — a
directory a normal user cannot traverse — it retries via `sudo` on a real TTY and strips `\r`.

**A new check, aimed squarely at the failure this script exists for.** The staged copies in
`/tmp/etv-deploy` are md5-compared *before* anything privileged runs, and the file count is
asserted. Yesterday's silent failure was a transfer that delivered nothing, so the transfer is
now proven before `install` is allowed to propagate it. Both verification loops assert the
count as well, so a short listing cannot pass as success.

Tested locally: syntax clean, and the hash-comparison loop was exercised against synthetic
`md5sum` output with CRLF line endings and one deliberately wrong hash — it parsed all three
rows, flagged the wrong one and returned non-zero.

**Files touched:** `scripts/deploy_ersatztv.sh`, `docs/logs/changes-tracker.md`.

## 2026-10-11 (2) — Meet the Fockers is a PAL/NTSC subtitle, and so are 427 others

Reported symptom: *"currently playing Meet The Fockers, and the subtitle is way out of sync,
several minutes. In plex on demand, it plays in sync."*

Measured, and it is not ambiguous. The video is a 25 fps PAL rip
(`Meet The Fockers KLAXXON.avi`, 108.7 min); its English subtitle's last cue lands at
113.3 min. Ratio 1.0425, against 25/23.976 = 1.0427. The subtitle was timed for the
23.976 fps release. The error grows linearly: about 2 seconds at the first cue, 76 seconds
half an hour in, 4 minutes 39 seconds by the closing credits. The Hungarian subtitle for the
same file is stretched identically (1.0426), so the whole subtitle set came from the NTSC cut.

**I read that as a property of the subtitle file. See the retraction below — the same ratio is
equally consistent with the video's declared frame rate being wrong, and the evidence now favours
that reading.** It does still correct my judgement from the previous entry. Top Gear S10E03 was a head shift (ratio 1.0104, first cue at 0) and really is
a one-off, but I concluded from it that mistimed subtitles were not worth tooling for. Re-running
`subtitle_sync_audit.py` against the refreshed inventory says otherwise:

      items with an external 'en' subtitle   2103
      subtitle ends past the end of video     637  (30%)
        of those, a PAL/NTSC stretch             428

428 files are repairable by one arithmetic pass — multiply every timestamp by 0.95904. The
remaining 209 belong to a different cut and need replacement subtitles. Worst affected:
Friends 192, 7th Heaven 157, Ally McBeal 68, How I Met Your Mother 47, Two and a Half Men 45,
films 44, TaleSpin 33, Top Gear 20.

### RETRACTION — the subtitle is probably correct and the VIDEO's framerate is probably wrong

I first explained the discrepancy as the two observations being made at different points in the
film: live was 90–110 minutes in (the guide shows the 20:00–22:00 slot on channel 1), on demand
was at the start, and `position × 0.0425` gives 3 min 50 s at 90 minutes against 2 seconds at the
first cue. That model is refuted by Plex's own database. `lastViewedAt` is 2026-10-11 22:05:38 with
`viewOffset: 240000` — a playthrough that reached 4 minutes, minutes before writing this. At 4
minutes the drift model demands a 10-second lag, which is impossible to miss, and none was seen.

So the timeline the Plex player follows agrees with the subtitle, and the subtitle's 113.3-minute
span is the film's real length. It is Plex's *declared* duration of 108.7 minutes that is 4.27%
short — which is the same ratio, pointing at the video's declared frame rate rather than at the
subtitle. Plex reports `videoFrameRate: PAL` (25 fps) for an AVI; if the header says 25 while the
content is 23.976, duration computed from the video header lands 4.27% short while playback
anchored to the audio stream runs the full length and stays in sync with an NTSC-timed subtitle.

### The frame-rate theory is dead too, and the real answer is Plex subtitle auto-sync

`ffprobe` from inside the ErsatzTV container — the same binary ErsatzTV transcodes with — closes
the frame-rate question completely:

      video  mpeg4  r_frame_rate 25/1  avg_frame_rate 25/1  time_base 1/25
             duration 6523.480  nb_frames 163087          (163087 / 25 = 6523.48)
      audio  ac3    duration 6523.488  nb_frames 203859   (203859 × 0.032 = 6523.488)
      format duration 6523.488

Every figure agrees to 8 ms. The file is a true 25 fps, 108.72-minute encode with no mislabelling
anywhere, so nothing about frame-rate handling can be blamed.

**The subtitle really is stretched, and two independent files prove it.** Scaling the English
subtitle by 0.95904 puts its last cue at 6523.6 s against a final frame at 6523.5 s — a miss of
0.1 s. The Hungarian subtitle, a separately authored file with 2564 cues against the English
file's 1867, lands at 6524.7 s, missing by 1.2 s. Cue density is flat across every ten-minute
bucket, so the stretch is uniform rather than a junk tail. Seventy English cues are timed to start
after the final frame and can never be displayed at all.

**So both of these are true at once, which is what I kept failing to see:** the `.srt` on disk is
stretched, *and* Plex plays it correctly. Plex is silently repairing it. The Media carries
`hasVoiceActivity: 1` and the subtitle stream carries `canAutoSync: 1`, and sampling 36 films shows
those two flags move together perfectly — 26 films have both, 10 have neither, and the pairing is
uncorrelated with whether the subtitle is flagged. They mark the files where Plex has finished
speech analysis and can therefore realign a subtitle at playback. That correction lives in Plex's
playback layer, not in the file, so ErsatzTV burning the raw `.srt` never sees it.

**Correcting one more of my own claims:** I said the flagged ratios "cluster hard" on 25/23.976.
They do not. Median deviation from the exact constant is 0.570%, and only 11% sit within 0.10% of
it. On a 110-minute film 0.570% is 38 seconds — far too loose to call a clean PAL/NTSC stretch. So
a blanket `× 0.95904` across all 428 is wrong; only the 127 files within 0.25% are good candidates
for the constant, and the rest need their subtitles replaced rather than rescaled. Meet the Fockers
is one of the clean ones, which is why its two files land within a second of the final frame.

**Files touched:** `docs/logs/changes-tracker.md`.

A repair script cannot locate the subtitles through the API — external subtitle streams expose
`key: /library/streams/{id}` but no `file` attribute, so the on-disk path has to be found by
globbing the video's own directory. That means the fixer has to run on the Plex VM.

**Files touched:** `ersatztv/audit/subtitle-sync-en.{txt,csv}` (regenerated),
`docs/logs/changes-tracker.md`.

## 2026-10-12 — `fix_pal_subtitles.py`: writing Plex's correction into the file

Plex repairs these subtitles at playback and ErsatzTV cannot see it, so the repair has to go
into the file. This does that, and only for the one case that can be proven.

**Scope.** A subtitle timed for the 23.976 fps master of a 25 fps PAL encode runs exactly
25/23.976 = 1.04271 too long. Every timestamp is multiplied by 23.976/25 = 0.95904 — a constant,
never a figure fitted to the file, so a subtitle that happens to overrun by some other amount
cannot be quietly bent into shape. Default tolerance is 0.25% from the constant, which across this
library selects 127 of the 428 overrunning files; the median deviation is 0.570% (38 seconds on a
110-minute film), so most overrunning subtitles are a different cut and are reported and skipped.

**Why it cannot do damage.**

- Dry run unless `--apply`.
- The original goes to `<name>.srt.orig` first, and a file that already has one is skipped, so
  re-running cannot rescale twice. Verified: a second `--apply` pass is a no-op.
- Rewriting happens on **bytes**, and only on lines that are a complete cue-timing line, anchored
  with `re.MULTILINE`. Subtitle text is never decoded, so the Windows-1250 and ISO-8859-2 files
  (most of the Hungarian ones) cannot be destroyed by an encoding round-trip. Verified against a
  cp1250 fixture: 48 high bytes before, 48 after, and the result is still not valid UTF-8 — which
  is the proof that no conversion happened.
- After writing it re-reads from disk and checks that the last cue lands on the final frame, that
  the cue count is unchanged, and that every byte outside the timing lines is identical. Any
  failure restores the backup.

**Why it has to run on the Plex VM.** Plex's API does not expose the on-disk path of an external
subtitle — only `/library/streams/{id}` — so the files can only be found by looking next to the
video. Durations come from `ffprobe` inside the ErsatzTV container, the same binary ErsatzTV
transcodes with, so the measurement and the burn agree by construction.

Tested on synthetic fixtures covering all four outcomes: a clean PAL pair (English and Hungarian
twins, both fixed, timings landing back on their exact original values), a subtitle from a
different cut (skipped at 14.67% deviation), one that ends inside the video (untouched), and a
re-run (skipped on `.orig`).

**Files touched:** `scripts/fix_pal_subtitles.py` (new), `docs/logs/changes-tracker.md`.

## 2026-10-12 (2) — A channel died on screen: zscale rejected an odd frame size

Photographed off the TV, mid-morning, immediately on tuning in:

      [Parsed_zscale_5] code 1027: image dimensions must be divisible by subsampling factor
      Last message repeated 9 times
      [fc#0] Error while filtering: Generic error in an external library
      [vost#0:0/libx264] Could not open encoder before EOF
      [out#0/hls] Nothing was written into output file, because at least one of its
                  streams received no packets.

Read bottom-up: the filter graph failed, so the encoder was never opened, so no packets ever
reached the muxer and the stream produced nothing at all. That is why it shows as a static error
card rather than a stutter — there was no video to send.

`zscale` raises code 1027 when a frame side is odd, because yuv420p subsamples chroma 2x2 and
cannot halve an odd number.

**Nothing in the library is odd**, so the odd size is being computed inside ErsatzTV. All 4957
media items were checked: zero have an odd width or height.

**Modelling `ScaleAndPad` into the profile's 1920x1080 reproduces odd sizes, and three of the six
channels were showing one at the time.** Fitting the display aspect inside 1920x1080 and rounding
to nearest gives:

      ch 2, 5   Jonny Quest S1E14    958x720   DAR 1.33  ->  1437x1080   ODD
      ch 6      Fantasia 2000        720x572   DAR 1.78  ->  1920x1079   ODD
      ch 1      Planet Earth III    1920x1080  DAR 1.78  ->  1920x1080   even
      ch 3      Toy Story           1920x1080  DAR 1.78  ->  1920x1080   even  (HDR)
      ch 4      Pan Am              1280x720   DAR 1.78  ->  1920x1080   even

**But the model over-predicts, and that has to be said.** 1019 of 4957 items fall in the same
at-risk class, and channels have been watched for days without this appearing. So either ErsatzTV
normally rounds to even and something tipped it over on this occasion, or the real trigger is
narrower than frame geometry alone. An earlier guess that HDR tonemapping was responsible — the
profile pins `bitDepth: EightBit`, so all 195 HDR items get a zscale conversion chain — does not
survive: only 11 HDR items also fit to an odd size, none were on air, and the HDR title that *was*
on air (Toy Story, ch 3) fits evenly.

Note also that a first pass at this put 2885 items at risk. That was wrong: it used Plex's
`aspectRatio`, which is rounded to two decimals, so an ordinary 1280x720 file reads as 1.78 rather
than 16/9 and fabricates a 1920x1079. Square-pixel sources must be measured from width and height.

**Still needed:** the ffmpeg command line from Troubleshooting → Playback for Jonny Quest S1E14 or
Fantasia 2000, which prints the computed dimensions and shows where the six zscale instances sit.
`Parsed_zscale_5` means at least six of them in one graph.

**Files touched:** `docs/logs/changes-tracker.md`.

## 2026-10-12 (3) — The crash is anamorphic scaling, and there is an upstream fix

Channel confirmed: **6 Filmek**, which at that moment was showing Fantasia 2000 — stored
720x572, displayed at 1.78, so genuinely anamorphic rather than square-pixel. Fitting that
display aspect into the profile's 1920x1080 gives **1920x1079**, and an odd height is exactly
what `zscale` refuses. The now-playing graphics overlay has never been enabled, so that is out.

**The upstream fix already exists.** Running version is 26.8.0; current release is v26.11.1.
Reading the notes between them:

      v26.8.1   2026-08-29  Security: GHSA-h3r4-r2f2-qf59 (CVE pending). Notes instruct
                            rotating the Plex token afterwards.
      v26.9.0   2026-09-06  XMLTV episode thumbnail fix. Nothing relevant.
      v26.10.0  2026-09-21  "Optimize anamorphic pipelines by only performing one scale
                            instead of two."  <-- this is the one
      v26.11.0  2026-10-05  Migrates ALL channels to the "next" streaming engine and makes it
                            the default. That engine ignores the ffmpeg profile's Thread Count,
                            Pad Mode, video Profile, video Preset and Allow B-Frames.
      v26.11.1  2026-10-06  QSV/VAAPI padding fixes, software pad fallback.

Two scales in an anamorphic pipeline means an intermediate frame size, and an intermediate size
is where an odd value can appear and then be handed to `zscale`. 26.10.0 removes that second
scale. It also happens to be the last release before the streaming engine changes underneath us.

**Decision: go to v26.10.0, not v26.11.1.** It carries the security fix and the one change that
targets this bug, without simultaneously swapping the streaming engine — doing both at once would
make it impossible to attribute whatever happens next, and several other threads are still open.
26.11.x should be a separate, deliberate step.

`ghcr.io/ersatztv/legacy` was checked directly against the registry: v26.8.1, v26.9.0, v26.10.0,
v26.11.0 and v26.11.1 all resolve, so this is a tag change and a pull, nothing more.
(`ghcr.io/ersatztv/ersatztv` is the development repo — commit-hash tags only, no `latest`.)

`ETV_IMAGE` in the install script is now pinned to `v26.10.0` instead of `:latest`. Re-running the
installer rewrites `docker-compose.yml`, so on `:latest` the version moves silently — and ErsatzTV's
schema migrations do not reverse.

**Unrelated but confirmed while looking:** the schedule deploy did land. Tuesday on channel 1 reads
09:20 cartoons, 10:00 Birth of the Solar System, 10:47 How It's Made, 11:09 Ancient Megastructures,
**12:00 The Celestine Prophecy (a film)**, 13:35 Georgie & Mandy, 14:00 Northern Exposure, 14:45
Ultimate Factories, **16:00 The King's Speech** — the matinee, the merged documentaries and the
afternoon film all present. 7th Heaven appears 10 times in the guide, all on channels 2 and 5.

**Files touched:** `scripts/install_ersatztv_plex_vm.sh`, `docs/logs/changes-tracker.md`.

## 2026-10-17 — The "out of schedule" cartoon is the guide lying about a 4-minute gap

Reported: channel 1 showed Ancient Megastructures with about 3 minutes still to run at 11:57,
but it ended and an unannounced cartoon started. On a previous occasion the cartoon then ran past
12:00 instead of stopping, and froze; restarting the client picked up the real programme.

Measured, and the arithmetic is exact:

      XMLTV guide entry   11:08:25 - 12:00:00   =  51.6 minutes
      the actual file      S01E05 The Alhambra  =  47.48 minutes
      so it really ends   11:55:54, leaving        4.1 minutes of gap

The same episode appears later in the same guide as 14:00:00-14:47:28, i.e. 47.5 minutes — its
true length. Only the entry that sits at the end of a `pad_until` block is stretched.

**Both halves are working as designed.** `pad_until: "12:00"` fills the block with whole items —
`discard_attempts: 12` tries twelve candidates for one that fits, and 4.1 minutes is shorter than
anything in DAYTIME_MIX, whose shortest items are How It's Made at 21-28 minutes. So the remainder
goes to `fallback: "FILLER"`, and the docs are explicit about what fallback filler is: *"filler
that is looped and cut as needed to fill any remaining gaps."* ErsatzTV then hides fallback filler
from XMLTV and extends the preceding programme's stop time over it, which is why the guide claims
three minutes that no longer exist. Nothing is misconfigured and nothing crashed.

**A remainder at every boundary is structural.** Padding a block with 20-50 minute content leaves
whatever does not divide evenly, so a few minutes of filler before each daypart is the normal case,
not an exception.

**The trim works; the freeze is intermittent.** Observed directly at 12:08 the same day: the
cartoon was cut mid-item and the 12:00 film started on the clock, exactly as "looped and cut as
needed" promises. So the earlier overrun-then-freeze was not a broken trim.

That reframes it as most likely client-side. The report was that the cartoon "ran till the end and
then frozen" and that "closing and opening the app started the real program" — a server that had
moved on while the Plex client sat on a stale buffer behaves precisely that way, and reopening the
app rejoins the live edge. Nothing in ErsatzTV's own behaviour needs to be wrong for that. Worth
noting that removing the fallback at these boundaries also removes one transition from the
sequence (episode straight to film, rather than episode to filler to film), so there is one fewer
opportunity for a client to stumble.

Still running 26.8.0 — the upgrade decided on 2026-10-12 has not been done.

**There is no alternative filler pool.** Searching the inventory for 1-9 minute items: Cartoons 296
episodes (273 TV-G, 25 unrated), Other videos 18 — which are family videos, not broadcast material
— Demos 2, TV Series 2. Widening to 15 minutes only adds 65 more cartoons. So short-form cartoons
are the only thing available to fill a gap on an adult daytime channel unless idents or bumpers get
made.

**Files touched:** `docs/logs/changes-tracker.md`.

## 2026-10-17 (2) — Let the film start early instead of filling the gap with a cartoon

Answering "cant we start the movie at 11:57?" — yes, and the docs say how. From the `pad_until`
reference:

      offline_tail - When true, after scheduling everything that will fit, any remaining time
                     will be unscheduled (offline). Default is false.
      fallback     - The "key" for content that should be used to fill any remaining unscheduled
                     time. One item will be selected from the content to be looped and trimmed
                     to exactly fit.

So the remainder is unscheduled unless a `fallback` claims it, and with `offline_tail` defaulting
to false it is not held open as dead air either — the playout simply moves to the next
instruction. Dropping the fallback therefore starts the next programme early, and the guide says
so, instead of stretching the previous entry over a hidden cartoon.

**Dropped from three pads on both Main channels: 12:00, 16:00 and 20:00.** Those are exactly the
jarring cases, because each is followed by a film.

**Kept on the other four, because dropping them would start a more permissive block early.** The
test is not "next source vs this source" but "next source against the ladder cap at the earlier
time":

      pad 12:00  DAYTIME_MIX   -> MATINEE         ceiling 10, cap before 14:00 is 10   DROPPED
      pad 14:00  DAYTIME_MIX   -> AFTERNOON_MIX   ceiling 14, cap before 14:00 is 10   kept
      pad 16:00  AFTERNOON_MIX -> AFTERNOON_FILM  ceiling 14, cap from 14:00 is 14     DROPPED
      pad 18:00  AFTERNOON_MIX -> EVENING_MIX     ceiling 14, cap from 14:00 is 14     kept
      pad 20:00  EVENING_MIX   -> FEATURE_FILM    ceiling 16, cap from 18:00 is 16     DROPPED
      pad 22:00  EVENING_MIX   -> NIGHT_FILM      unrestricted, cap before 22:00 is 16 kept
      pad 10:00  CARTOONS      -> DOCUMENTARY     a cartoon gap inside the cartoon block
      pad 06:00  NIGHT_MIX     -> repeat          `wait_until 06:00` would leave the gap offline

The 18:00 one would pass today only because `EVENING_MIX` happens to contain nothing rated above
TV-14 — the cap there is 16. Keeping the fallback means the guarantee does not depend on what the
pool happens to hold.

**Two corrections to figures I produced along the way.** First, my ceiling calculation initially
reported `AFTERNOON_FILM` and `FEATURE_FILM` as 99 because the age map did not know `hu/14`,
`hu/PG-13`, `12` or `hu/16 éven aluliak számára nem ajánlott`; mapped properly they are 14 and 16.
Second, `validate_ersatztv_queries.py` crashed with `KeyError: 'query'` the moment it was run,
because marathon sources carry `searches` instead. Fixed to sum across them — DAYTIME_MIX now
reports 1048 items over 2 searches, AFTERNOON_MIX 2041 over 2.

New hashes to deploy: `main.yml` `e56dda2e8e235570e8f2d42f440027e9`,
`main-hu.yml` `9df6955d5a246abc87450664544a7f41`. The other four are unchanged.

**Files touched:** `ersatztv/main.yml`, `ersatztv/main-hu.yml`,
`scripts/validate_ersatztv_queries.py`, `docs/logs/changes-tracker.md`.

## 2026-10-17 (3) — All six daypart fallbacks dropped, and what that actually costs

Deployed in the afternoon, and the 22:00 boundary did it again: Georgie & Mandy, then a few
minutes of Tom and Jerry, then the film at 22:00. That was the expected consequence of the
previous entry — 22:00 was one of the three pads whose fallback was deliberately kept.

The guide confirms the other three now behave as intended. Main, next two days:

      12:00 matinee   11:58:48 The Party            11:59:37 Animals are Beautiful People
      16:00 film      15:58:58 Coyote Ugly
      20:00 feature   19:51:02 Independence Day
      22:00 night     22:00:00 Definitely, Maybe    <- pinned, hence the cartoon

Asked to extend it to 14:00, 18:00 and 22:00 as well, which is now done on both Main channels.
Only two pads keep a fallback: 10:00 (a cartoon gap inside the cartoon block is invisible, and it
holds the day's one documentary on the clock) and 06:00 (`repeat` leads to `wait_until: "06:00"`,
so the gap would go offline rather than start anything early).

**The exposure this accepts is larger than the four minutes that prompted it, and that should be
on the record.** The early start is bounded by the shortest item the pool can offer, not by a few
minutes, because when nothing fits the entire remainder passes to the next instruction. Measured
across the pools:

      source           items  shortest  10th pct  median
      DAYTIME_MIX       1048       17m       20m     22m
      AFTERNOON_MIX     2040        1m       20m     41m
      EVENING_MIX       1954        1m       20m     41m

Starts 10.8 minutes early were already observed at the 20:00 boundary, so ~20 minutes is the
realistic worst case. Concretely: `AFTERNOON_MIX` at TV-14 can now begin inside the cap-10
window, and `NIGHT_FILM`, which has no rating ceiling at all, can begin before 22:00. That is a
deliberate trade, recorded here so it is not rediscovered as a bug.

If the exposure ever matters more than the interruption, `fallback: "EVENING_MIX"` on the 22:00
pad would hold the clock exactly with rating-appropriate content rather than a cartoon — at the
price of one truncated episode, since fallback content is looped and trimmed to fit. Noted in the
file at each affected pad.

**Also fixed two comments that the change had made false:** the `WHY EVERY BOUNDARY IS trim: false
WITH A FALLBACK` header in both files, and an "optional refinements" note at the foot of main.yml
that still advised putting `fallback: "FILLER"` on every `pad_until` — the exact thing just
reversed.

New hashes: `main.yml` `6f2e397f27127d141ebaf33e2b48eea4` before the comment rewrite; see the
deploy output for the final pair.

**Files touched:** `ersatztv/main.yml`, `ersatztv/main-hu.yml`, `docs/logs/changes-tracker.md`.

## 2026-11-01 — Multiple audio and subtitle tracks for the client: not possible with Plex

Asked whether ErsatzTV could push both audio tracks (and subtitles) so the viewer picks in the
Plex UI, rather than running paired Hungarian and English channels. The answer is no, and the two
reasons compose into a hard wall.

**Audio.** From the ErsatzTV maintainer, closing legacy#1923 ("Is it possible to stream more than
one audio track?"):

> Generally speaking, no, ETV will only process a single audio track. The only exception to this
> is using `HLS Direct` which will send all (unprocessed) audio tracks when the schedule item and
> channel have no preferred audio language and no preferred audio title.

That matches the channel docs, where both the Default and the Custom stream selector are described
as selecting *one* stream. Two further feature requests asked for exactly this — legacy#1421
"[Feature Request] Second Audio Track for Channels" and legacy#1381 — and both were closed by the
stale-issue bot without being implemented.

**Subtitles.** A selectable subtitle track does exist now: v26.5.0 added `Next Engine Text Subtitle
Mode` with `Burn` (the default) and `Convert If Possible`, which converts text subtitles to WebVTT.
But v26.11.3 is explicit about where that can go:

> Only advertise the HLS subtitle track when the channel's text subtitle mode is `Convert`
> MPEG-TS streams no longer request the HLS subtitle track, which they cannot use

**And the wall is the client.** From the Plex client page: *"The only channel streaming mode
supported directly by Plex clients is MPEG-TS."* So the one mode that carries all audio tracks
(HLS Direct) and the one that can carry a subtitle track (HLS Segmenter) are both unavailable to
Plex. MPEG-TS gets one burned-in subtitle and one audio stream, by construction.

HLS Direct is not a workaround worth chasing even with a different client: it does not transcode,
so a channel that mixes a 592x320 mpeg4 AVI with 4K HEVC would hand the client a new codec and
resolution at every programme boundary. The whole reason the ffmpeg profile normalises everything
to 1920x1080 H264 AAC is that this library is not uniform.

**So the paired channels stay.** Six channels is the workaround, not a design mistake, and the
single audio stream per channel is why they exist.

**Incidental, and relevant to the 17 Oct freeze:** legacy#2200 is titled "Playout Gets Stuck
Playing Fallback Filler On Transition Between Post-Roll Pad Filler And ...". That is close enough
to the overrun-then-freeze symptom to be worth remembering, though it is moot now that the daypart
fallbacks are gone.

**Confirmed while checking:** running version is `26.10.0-docker-amd64`, the pinned target. The
upgrade was done. `/api/version` now returns 401, so the API key really did become mandatory and
those diagnostics are closed to me; `/iptv/xmltv.xml` and the web UI still answer.

**Files touched:** `docs/logs/changes-tracker.md`.

## 2026-11-02 — Yes it is open source, no fork needed: stream copy shipped in v26.11.0

Asked whether ErsatzTV is open source, whether we could fork it, and whether a fork could send
files to Plex without encoding — *"its stupid that we need to encode now, but not when playing on
demand"*.

**Open source, and permissively licensed.** `ErsatzTV/legacy` is C# under **zlib**, 25 MB, 3030
stars, 0 open issues, pushed today. `ErsatzTV/next` is **Rust** under **MIT**, 13 MB, 217 stars.
Both licences permit forking without conditions, so the question is only whether it is worth it.

**It is not, because the feature already exists.** From the v26.11.0 notes, under "Next engine":

> FFmpeg Profiles with `Normalize Video` or `Normalize Audio` disabled now copy that stream; they
> were previously transcoded to `h264` / `aac`
>   - Items that cannot be copied are transcoded using the profile's settings
>     - e.g. items with burned-in subtitles, still images, and source codecs that are not copied
>       by default
>     - `h264` / `hevc` video can be copied by default, `aac` / `ac3` / `eac3` / `mp3` audio can
>       be copied by default

That is exactly the request: copy what already matches, transcode only what does not.

**Why it was ever transcoding everything** is worth stating, because the instinct that on-demand
"just plays the file" is right but does not transfer for free. Plex on demand plays one file and
the client negotiates codec and resolution for that file. A linear channel is a single continuous
stream, so historically every item had to be normalised to one codec and resolution or the client
would break at each boundary. The next engine attempting per-item copy means it is now handling
those discontinuities itself — whether **Plex's** MPEG-TS client tolerates them is an empirical
question, not something the release notes answer.

**Four caveats, all stated upstream:**

- Items with **burned-in subtitles cannot be copied**. The English channel burns English subtitles
  over Hungarian audio, so those items still transcode; the items hitting the selector's
  `disable_subtitles: true` tier can be copied.
- **"Watermarks and graphics are not applied to copied video."** If `now-playing.yml` is ever
  wired in, it would silently vanish on copied items.
- With `Normalize Frame Rate` enabled, only items already at the target rate are copied. Harmless
  here — the profile has `normalizeFramerate: false`.
- The next engine ignores `Thread Count`, `Pad Mode`, video `Profile`, video `Preset`,
  `Allow B-Frames`, `VAAPI Display`, `QSV Extra Hardware Frames` and `Normalize Colors`. The
  current profile sets `veryfast`, `main` and `allowBFrames: false`, all of which become inert.

**This supersedes the 2026-10-12 decision to hold at v26.10.0.** That was to avoid swapping the
streaming engine while other things were unresolved. The capability now wanted lives in exactly
that engine, and v26.11.0 provides a per-channel escape hatch — *"To roll back a channel, set
`Streaming Engine` to `Legacy` in the channel editor"* — which makes trying it reversible one
channel at a time.

**And if copy turns out not to work through Plex, the quality complaint has a cheaper fix.** The
profile encodes 1920x1080 at **2500 kbps** with `veryfast` and no B-frames, which is low enough to
explain on its own why a channel looks worse than the same file on demand. Raising the bitrate
costs nothing but bandwidth.

**Files touched:** `docs/logs/changes-tracker.md`.

## 2026-11-02 — Plex moved to an LXC with an AMD iGPU; the repo lost everything again, twice over

### The work was destroyed a second time, and is now committed

`ersatztv/` and every Python helper were gone from the working tree again. Noticed only because
the v26.10.0 image pin added on 12 October had silently reverted to `:latest` — an edit vanishing
is a better alarm than a missing directory, since nothing announces the latter.

Cause is the same as 11 October: this work had never been committed, and a branch checkout
followed by a reset to `origin/main` discards untracked and uncommitted files alike. Two dangling
checkpoint commits survived in the object store:

      a6a51e0  2026-10-11 21:42  main.yml 33e77d2b  (pre-fallback-change state)
      62696bc  2026-10-25 11:21  main.yml dbbb6fdf  (exactly the 17 Oct final state)

Recovered from `62696bc`, selectively — `git checkout 62696bc -- ersatztv/` plus the seven missing
scripts by name, deliberately NOT `scripts/` wholesale, because that would have reverted
`install_ersatztv_plex_vm.sh` (edited minutes earlier) and `scripts/wall-panel/` (advanced by
several commits since). All eight hashes verified identical to the deploy targets, and
`check_watershed.py` passes.

**Everything is now committed**, and `__pycache__/` plus `*.pyc` added to `.gitignore` so future
commits stay clean. The changelog itself was never at risk: being tracked, it got swept into one
of the wall-panel commits and survived both events.

### Plex now runs in an LXC with an AMD iGPU, and ErsatzTV did not follow

Plex answers on 32400 (1.43.5.11079); ErsatzTV on 8409 does not answer at all. A fresh install was
chosen over migrating the old config.

**Docker over the native binary, and the GPU is the reason — not against it.** The script's own
header already recorded the argument: ErsatzTV is tightly coupled to a specific FFmpeg build, and
the native path has a known failure mode where an upgrade leaves the service dead because bundled
FFmpeg was not upgraded with it (community-scripts/ProxmoxVE#5443). v26.11.0 tightens this
further — *"Use ErsatzTV-ffmpeg 8.1.2-4 in docker images… releases are now immutable; docker
images pin them by digest"* — so the image carries the exact VAAPI-capable build the maintainer
tests. Native would mean fetching ErsatzTV-FFmpeg by hand and keeping it in sync, and a stale or
distro ffmpeg is precisely where VAAPI support fails.

The usual objection to Docker-in-LXC is GPU permissions, and here it mostly does not apply: the
hard hop, Proxmox host to LXC, is already solved by Plex using the iGPU. What remains is LXC to
Docker, which the script already handles — it stats `/dev/dri/renderD128` for its GID as seen
inside the host and emits `devices: /dev/dri:/dev/dri` with a matching `group_add`, which is
correct whether the LXC is privileged or carries an idmap for the render group.

**Installer updated:** pinned to `v26.11.6` (next engine, so stream copy is available), the GPU
block now warns instead of shrugging when `/dev/dri` is absent, "Plex VM" reworded to "Plex host"
throughout, LXC prerequisites documented (`nesting=1`, `/dev/dri` bound), and every hardcoded LAN
address removed per AGENTS.md — the closing summary now resolves the address at runtime via
`hostname -I`, since this host changed once already and silently invalidated every baked-in URL.

**Files touched:** `scripts/install_ersatztv_plex_vm.sh`, `.gitignore`,
`docs/logs/changes-tracker.md`, plus `ersatztv/` and seven scripts recovered from `62696bc`.

---

## 2026-11-18 — The GPU probe was looking for the wrong device node

The LXC's config settled two of yesterday's open questions and exposed a bug in the installer:

```
dev0: /dev/dri/renderD129,gid=992
features: nesting=1
mp0: /tank/media,mp=/mnt/media,ro=1
```

`nesting=1` is already set, so Docker will start. But the iGPU arrives as **renderD129**, and the
GPU probe tested `[ -e /dev/dri/renderD128 ]` — a literal hardcode. On this host it would have
fallen through to the "no /dev/dri" branch and installed a CPU-only ErsatzTV while printing a
warning that reads as a hardware problem rather than a script bug. That is the exact silent
downgrade the block was written to prevent, caused by the block itself.

The node number is not a constant: it depends on how many DRM devices the kernel enumerated, and
the container is passed exactly one node. Detection now prefers `renderD128` when present and
otherwise takes the first `renderD*` in the directory, reads the GID from whichever it found
(992 here, matching `dev0`), and prints the path. Because ffmpeg's own default VAAPI device *is*
renderD128, it also prints a reminder to point the FFmpeg Profile at the real node when they
differ — otherwise hardware encoding fails at playback despite a correct install.

**The media preflight was also written for the old world.** It was built around NFS with
`x-systemd.automount` on a VM, where a dead mount presents an empty directory rather than an
error. The LXC gets a read-only ZFS bind mount instead, so: `zfs` joins `nfs|nfs4` as an expected
fstype, the stale "is the NFS mount in fstab?" message now points at `pct config <ctid>` and
`mp0`, and the `mountpoint -q` test was demoted from fatal to a warning. That last one is a
deliberate narrowing: the check with teeth is the emptiness test below it, since what decides
whether ErsatzTV works is whether media is readable, not the shape of the mount. The silent-empty
case that motivated the original guard still fails the install.

Verified with `sh -n` and by simulating both detection paths (renderD129-only picks renderD129;
no directory picks nothing).

**Files touched:** `scripts/install_ersatztv_plex_vm.sh`, `docs/logs/changes-tracker.md`.

---

## 2026-11-18 (2) — ErsatzTV is up on the LXC with working VAAPI

The install ran. ErsatzTV reports `26.11.6-docker-amd64`, serves HTTP 200 on 8409, and
generates an empty XMLTV guide (0 programmes), which is correct with no channels defined yet.
Plex is unaffected on 32400.

**Hardware encoding is confirmed working, not merely detected.** Inside the container:

```
crw-rw---- 1 root 992 226, 129 Nov 15 23:00 renderD129
VAAPI ENCODE OK
```

The group on the device node is 992, matching the LXC's `dev0: …,gid=992`, so Docker's
`group_add` is correct. The second line is an end-to-end `h264_vaapi` encode through
`-init_hw_device vaapi=va:/dev/dri/renderD129`, which proves device visibility, group
permissions and encoder initialisation together. Worth doing as one test rather than trusting
the installer's probe, since every previous GPU problem here has been a permission or path
issue that a presence check cannot see.

**Why the image is `legacy` and not `next`.** Asked and worth recording. They are two
products, not two versions. ErsatzTV Next "aims to provide a lighter alternative to all-in-one
systems like ErsatzTV Legacy by focusing on transcoding and streaming, supported by
third-party library management and scheduling tools. A basic scheduler is included for
demonstration and reference purposes." This configuration *is* a scheduler — six dayparted
sequential schedules, Plex library import, custom stream selectors — so Next would mean
rebuilding all of it against JSON configs that are still taking breaking changes (channel
format 0.1.2, playout 0.0.6, parts unreleased). Nothing is given up by staying: legacy v26.11.x
embeds the next engine per channel, which is where stream copy lives — the Next docs address
"ErsatzTV (legacy) users with next engine channels" directly. Direction of travel noted: the
docs banner promises legacy only "security updates for the foreseeable future" and the
announcement is titled *Unarchiving ErsatzTV Legacy*, so legacy is in long-term maintenance and
the eventual path is Next plus an external scheduler. Not a decision for today.

**`ersatztv/README.md` corrected** — it is the document the rebuild follows, and three claims
in it had become false:

- It described transcoding as "CPU-only, since the RTX A2000 is passed through to the LLM VM".
  Now VAAPI on the iGPU, with the `renderD129`-not-`renderD128` trap and the verification
  command written down, because that one fails at playback rather than at install.
- It claimed `main.yml` and `kids.yml` use `trim: true` and clip programmes at boundaries.
  Verified false: every pad is `trim: false`. Rewritten to describe what the files actually do
  — dayparts start early rather than clipping, `main*.yml` keeps only two fallbacks after
  2026-10-17, `kids*.yml` holds the clock with `SHORT_CARTOONS`, `movies*.yml` uses `count` —
  and to state the watershed exposure an early start creates.
- The "Deploying" section still showed hand-rolled `scp`/`cp` with a hardcoded address. Now
  points at `scripts/deploy_ersatztv.sh`, with the reason it exists (the 2026-10-10 silent
  stale deploy). Last hardcoded addresses in this file are gone, per AGENTS.md.

**Files touched:** `ersatztv/README.md`, `docs/logs/changes-tracker.md`.

---

## 2026-11-18 (3) — The container clock was UTC, an hour behind local

`docker exec ersatztv date` reported UTC, one hour behind CET. The installer was not at
fault: it derives `TZ` from the host (`timedatectl show -p Timezone --value`, falling back to
`/etc/timezone`), and the LXC itself is UTC, as a freshly built container usually is. It
copied the host faithfully.

**Why this is the worst kind of bug for this particular system.** Every boundary in the six
schedules is wall-clock local time — the daypart changes at 10:00, 12:00, 14:00, 16:00, 18:00,
20:00, and the 22:00 watershed. An hour of skew moves all of them. Unrestricted `NIGHT_FILM`
content would begin while a UTC-correct clock still reads 21:00 local, and the age ladder that
`scripts/check_watershed.py` verifies in the YAML would be enforced against the wrong hour.
Nothing downstream looks broken: no error, no failed playout, no yellow build. The
programming is simply wrong. Caught before any playout was built, so no bad guide was ever
published.

Fixed at both layers — `timedatectl set-timezone Europe/Budapest` in the LXC, then `TZ` in
`/opt/ersatztv/docker-compose.yml` and `systemctl restart ersatztv`, which recreates the
container because the unit's `ExecStart` is `docker compose up -d`.

**Installer hardened so it cannot happen quietly again:**

- When the resolved timezone is `UTC` or empty, it now warns to stderr with the fix for both
  layers. Deliberately a warning and not a failure: UTC is a legitimate choice on some hosts,
  and the script cannot know the intent. What it can do is refuse to be silent.
- The verification block now prints `docker exec ersatztv date` with a note that it must match
  the wall clock. Printed rather than asserted, for the same reason.
- The verification block also now runs the real `h264_vaapi` encode test through
  `-init_hw_device vaapi=va:${RENDER_NODE}`. The existing probe only proved the device node
  exists; this proves ffmpeg can encode through it, which additionally covers group
  permissions and driver availability inside the container. Non-fatal, but it turns a silent
  CPU fallback into a visible line at install time.

Both additions follow the same principle as `deploy_ersatztv.sh`: the failures that cost time
here are never the loud ones.

**Files touched:** `scripts/install_ersatztv_plex_vm.sh`, `docs/logs/changes-tracker.md`.

---

## 2026-11-18 (4) — Every `hu/*` content rating clause matches nothing, and now we know why

The ErsatzTV web UI has no authentication, so the live search index can be queried with plain
GETs. That turned the long-standing MATINEE mystery from a hypothesis into a measurement, and
the answer is worse in scope than expected but fail-safe in direction.

**The finding.** ErsatzTV's index splits content rating values on the forward slash. Measured
against the live index:

```
content_rating:"hu/KN"        0        content_rating:hu            710
content_rating:"hu/12"        0        content_rating:12            227
content_rating:"hu/16"        0        content_rating:(hu AND KN)    13
content_rating:hu\/12         0        content_rating:(hu AND 12)   226
content_rating:"hu 12"        0        content_rating:(hu AND 16)   305
```

So `hu/12` is indexed as two separate terms, `hu` and `12`. No quoted, escaped or phrase form
matches it; the working form is a boolean AND of the tokens. **Every `content_rating:"hu/…"`
clause in all six schedules has therefore always matched zero items** — hu/KN, hu/6, hu/12,
hu/14, hu/16, hu/PG-13 and the long `hu/16 éven aluliak…` variant.

**It is only the slash.** Hyphens are fine, which matters because it means the episode-side
failsafe was never broken: `content_rating:"TV-G"` returns 50 and
`show_content_rating:"TV-MA"` returns 695. The `NOT show_content_rating:"TV-MA"` guard on every
family source has been doing its job all along. Interestingly the reverse holds for hyphens —
`show_content_rating:(TV AND MA)` returns 0 — so a hyphenated value is one token and a slashed
value is two.

**The MATINEE gap is explained exactly.** The source was measured at 25 by the local model and
returned 12 live; there are 13 `hu/KN` films; 25 − 13 = 12. Hypothesis confirmed by
measurement rather than inference.

**The direction of the bug is fail-safe, which is why it was never visible as a breach.** Each
age gate is an allow-list, so a clause that matches nothing *excludes* content rather than
admitting it. Nothing ever aired above its daypart ceiling because of this. What it did instead
was starve the film sources, measured before and after the fix:

| Source | Now | Corrected | Gain |
|---|---|---|---|
| `MATINEE` | 28 | 41 | +13, exactly the `hu/KN` films |
| `AFTERNOON_FILM` | 291 | 313 | +22 |
| `FEATURE_FILM` | 283 | 593 | +310, mostly the 305 `hu/16` films |

`FEATURE_FILM` is the 20:00 prime slot and it has been running on less than half the catalogue
it was written to use. Note that `hu/12` content did partly leak in through the bare
`content_rating:"12"` clause, because `12` is one of the two tokens of `hu/12` — which is why
these sources were thin rather than empty.

**Applying the fix moves reality toward the model that was already verified.**
`check_watershed.py` evaluates the YAML allow-lists on the assumption that `hu/*` clauses work,
so it has been checking the intended programming all along. Correcting the queries makes the
live behaviour match what was already proven safe, rather than introducing anything new.

**New tool: `scripts/count_ersatztv_queries.py`.** Counts every content source against the live
index and flags any that match nothing, which is dead air ErsatzTV never warns about. It
complements `validate_ersatztv_queries.py` rather than replacing it: that script reimplements
the query language against a Plex CSV and so explains *why* a count is what it is, but a local
model structurally cannot discover something like slash tokenisation. This one asks ErsatzTV.
Read-only — it reads the count from the server-rendered HTML and never saves a search, adds to
a collection, or touches a playout. Also takes `--query` for ad-hoc counts, which is how the
whole investigation above was done.

**Current scan state (incomplete).** Movies 868 of 900, Cartoons 14 shows / 783 episodes of
15 / 819, TV Series 63 / 3410 of 63 / 3413. All five required libraries are enabled for sync
and the two junk libraries are correctly off, so the shortfall is scan progress, not
configuration. Counts above will rise slightly.

**Files touched:** `scripts/count_ersatztv_queries.py` (new),
`docs/logs/changes-tracker.md`.

---

## 2026-11-18 (5) — The `hu/*` fix applied, and the safety net nearly went vacuous doing it

Rewrote every slashed rating clause across the six schedules: `content_rating:"hu/X"` becomes
`content_rating:(hu AND X)`, 62 clauses in total. Two variants were **dropped** rather than
rewritten — `"hu/16 "` with its trailing space, and the long
`"hu/16 éven aluliak számára nem ajánlott"` — because any value carrying both the `hu` and `16`
terms is already matched by `(hu AND 16)`. Verified live: nothing in the index carries an `éven`
term at all, and `(hu AND 16) NOT content_rating:éven` returns the same 305. Three clauses
expressing one condition is worse than one.

Measured effect on the live index:

| Source | Before | After |
|---|---|---|
| `main.yml` FEATURE_FILM | 283 | 593 |
| `main.yml` AFTERNOON_FILM | 291 | 313 |
| `main.yml` MATINEE | 28 | 41 |
| `main-hu.yml` FEATURE_FILM | 154 | 323 |
| `main-hu.yml` MATINEE | 10 | 19 |
| `movies.yml` COMEDY | 158 | 281 |
| `movies.yml` FAMILY_FILMS | 24 | 38 |
| `kids.yml` KIDS_MOVIES | 15 | 22 |

**The part worth recording is what nearly went wrong.** `check_watershed.py` passed immediately
after the rewrite — and the pass was almost worthless. `validate_ersatztv_queries.py`, whose
evaluator the checker imports, could not parse `field:(a AND b)`: its tokenizer's bare-value
alternative is `[a-z_]+:[^\s()]+`, which refuses to match across a parenthesis, so the field
name was dropped entirely and the clause silently disappeared. The effect was that
`FEATURE_FILM` dropped from 588 modelled items to 61, and a source matching almost nothing
passes any age ceiling trivially. The check had become a check of nothing.

It was not caught by reading the output, because the output said what it always says. It was
caught by diffing the model's counts before and after the change — and the first attempt at
that diff was itself wrong (it compared the wrong awk fields and reported no differences at
all, which looked reassuring). The lesson is the one this repo keeps relearning: a verification
step that cannot distinguish "passed" from "had nothing to examine" is not a verification step.

**Evaluator corrected to model what was measured**, not what was assumed:

- `TOK` gained a `[a-z_]+:\([^)]*\)` alternative, placed before the bare-value alternative.
- New `value_terms()` splits a rating on non-alphanumerics while keeping hyphens, so `hu/16`
  is two terms and `TV-MA` stays one.
- Term semantics apply **only** to `content_rating` and `show_content_rating`. `library_name`
  and the title fields stay exact, because `library_name:"TV Series"` matches 63 shows live
  while `content_rating:"hu 12"` matches nothing — the two field kinds demonstrably differ, so
  assuming one rule for all of them would be wrong in a way that is hard to notice.
- A bare `content_rating:"12"` now correctly matches `hu/12`, which is why those sources were
  thin rather than empty.

**Ten synthetic spot checks added** for these semantics, deliberately not title-based so they
keep holding as the library changes. They pin the non-obvious cases: `(hu AND 6)` must NOT
match `hu/16`, the long Hungarian variant must match `(hu AND 16)`, `show_content_rating:(TV
AND MA)` must NOT match `TV-MA`, and `library_name:"TV Series"` must stay exact.

**Verified after the fix:** spot checks pass, the model is back to 588 for `FEATURE_FILM`
(against 593 live — the model and the live index now agree, having disagreed by a factor of
nine before), and `check_watershed.py` exits 0 with every source inside its ceiling *while
actually examining the 305 `hu/16` films* that the 20:00 slot will now serve.

Library inventory regenerated first: 5334 rows, up from 4224.

**Still open:** all ten sources in `movies-hu.yml` model as 0 items, and did so before this
change too, so the watershed check has never had anything to examine for the three `-hu` files.
Suspect the model does not implement `language_tag`. The live counter does not share this blind
spot and reports healthy numbers for those files, but the modelled check should be fixed.

**Files touched:** the six `ersatztv/*.yml` schedules,
`scripts/validate_ersatztv_queries.py`, `ersatztv/audit/*`, `docs/logs/changes-tracker.md`.

---

## 2026-11-18 (6) — The Hungarian schedules had never been watershed-checked, and one had drifted

**The literal question was why `movies-hu.yml` modelled as 0 items.** Cause confirmed: every
Hungarian query ends `AND language_tag:hu*`, the audit CSV has no audio-language column, and an
unknown field evaluates False — so the whole conjunction collapsed. A zero passes any age
ceiling, so `check_watershed.py` had been checking nothing for all three `-hu` files.

**Fixed by sound over-approximation rather than by modelling languages.** All 18 real uses of
`language_tag` are `AND language_tag:hu*` at the top level — purely narrowing, never negated,
never inside an OR. So relaxing that one conjunct yields a superset of each real source, and an
age ceiling that holds for a superset holds for every subset. It is also sound for timing:
`earliest_starts()` advances the clock by a source's shortest item, a superset's shortest item
is no longer than the real one, so later sources meet a ceiling at least as strict.

Modelling languages properly was considered and rejected. It would cost ~5,300 extra Plex
requests per audit, and it carries exactly the risk that produced the `hu/*` slash bug: ErsatzTV
reads languages from its own stream metadata, and a Plex-derived model could be confidently
wrong about what ErsatzTV actually indexes. Over-approximation cannot be wrong in the dangerous
direction, and real counts are already available from the live counter.

The over-approximation is guarded, not merely asserted: `tokenize()` raises if an
over-approximated field ever appears negated, inside an OR, or below the top level, since
"assume true" stops meaning "superset" in those positions. It refuses one form that is actually
sound — a nested AND — which is the safe way to be wrong. Spot checks pin the guard. Affected
counts print as `(upper bound)`.

Result: `movies-hu.yml` **was safe all along**. All nine of its language-filtered sources are
exact mirrors of `movies.yml`, and all ten sources now evaluate and pass.

**The checker's own justification turned out to be false.** Its docstring said the HU zeros were
harmless "by subset reasoning: every HU query is its EN counterpart plus
`AND language_tag:hu*`". Tested rather than trusted: **14 of 18** language-filtered HU sources
are mirrors. The four that are not — `main-hu.yml`'s `DAYTIME_MIX`, `AFTERNOON_MIX`,
`EVENING_MIX` and `NIGHT_MIX` — were covered by neither the EN check nor their own. A safety
argument that depends on an invariant nothing enforces is a hope.

**And the four that diverge had diverged in the unsafe direction.** Title exclusions added to
`main.yml` over time were never propagated to `main-hu.yml`:

| Source | Slot | Missing from HU |
|---|---|---|
| `DAYTIME_MIX` | 10:23, ≤10 | 7th Heaven, Showder Klub |
| `AFTERNOON_MIX` | 14:00, ≤14 | 7th Heaven, Showder Klub |
| `EVENING_MIX` | 18:00, ≤16 | Showder Klub |
| `NIGHT_MIX` | 00:06, any | Breaking Bad |

Measured live: Showder Klub is already blocked by the rating allow-list in all three, so its
exclusion is belt-and-braces. **7th Heaven is not: 22 Hungarian-audio episodes reach both the
10:23 and 14:00 slots.** English admits 7th Heaven to daytime only through a hand-curated set —
season 1 except episode 15, plus S10 E14 and E22. All 22 Hungarian episodes are season 2, and
none fall inside that set; no Hungarian-audio episode of the curated set exists at all.

**Fixing the checker alone would not have caught this.** 7th Heaven carries a permissive
show-level rating, so these episodes pass the ceiling — they print `[ok]` even now. The English
exclusion is an editorial override layered on top of ratings, which is precisely what a rating
check cannot see. It surfaced only because the two files were diffed.

**So drift is now its own check, and a failure.** `check_watershed.py` compares every shared
source's `NOT show_title:` exclusions between each EN/HU pair and fails on any the HU file
lacks. A deliberate divergence is declared in the HU file as a YAML comment, which ErsatzTV
ignores — `# drift-ok: KEY "Title" <reason>` — so a divergence must be a recorded decision
rather than an accident. It currently fails with the six above, which is correct: the
schedules should not pass while the question is open.

**Files touched:** `scripts/validate_ersatztv_queries.py`, `scripts/check_watershed.py`,
`docs/logs/changes-tracker.md`.

---

## 2026-11-18 (7) — CORRECTION to (6): the Hungarian schedule had not drifted

Entry (6) reported that `main-hu.yml` had "diverged in the unsafe direction" and that 22
episodes of 7th Heaven season 2 reached the 10:23 and 14:00 slots which "English admits only
through a hand-curated set". **That was wrong.** I diagnosed the divergence from the queries
alone without reading the comments that explain them, and `main.yml` states the opposite in a
section headed *"TWO SHOWS ARE HELD OFF THE ENGLISH CHANNEL ON LANGUAGE GROUNDS"*:

- **7th Heaven** is rated TV-G and documented as "genuinely family-appropriate". All 194 files
  come from one Hungarian release pack. The "curated set" — season 1 except episode 15, plus
  S10 E14 and E22 — is not an age decision. It is exactly the 19 episodes that carry an English
  audio track. Season 2 on the Hungarian channel at 10am is the intended programming.
- **Showder Klub** is Hungarian stand-up with no English audio.
- **Breaking Bad**'s only copies are Hungarian dubs; it "air[s] on main-hu.yml instead".
- `main.yml` says of these: *"Both shows remain on main-hu.yml, where they are correct."*

Verified mechanically as well: once those language-ground exclusions are set aside,
`DAYTIME_MIX`, `AFTERNOON_MIX` and `EVENING_MIX` are identical between the two files. The
English versions additionally carry one search re-admitting the English-audio 7th Heaven
episodes, which the Hungarian file does not need. `NIGHT_MIX` also adds Terapia, which `main.yml`
documents as belonging on `main-hu.yml`, and draws on TV Series alone rather than also Cartoons;
it is the 00:06 slot, which has no age ceiling. Every divergence is explained by the documented
design. **There was no exposure.**

What stands from (6): `movies-hu.yml` was safe all along; the Hungarian files had never been
watershed-checked because `language_tag` collapsed them to zero; the checker's own subset
argument was false for 4 of 18 sources; and the over-approximation fix is sound and makes all
three Hungarian files genuinely checked. All of that is unaffected.

**The drift check is kept, with its justification rewritten.** A `NOT show_title:` clause can
carry a LANGUAGE decision, where divergence is correct, or an AGE decision, where divergence is
a breach the rating check passes silently. The query does not say which. So the check still
fails on any EN exclusion its HU counterpart lacks, unless the HU file declares it. The six
language divergences are now declared at the top of `main-hu.yml`, each with its reason, under a
note that an exclusion added to `main.yml` for age reasons must be copied rather than declared.
The check's docstring now says plainly that it found six divergences on its first run, all
deliberate, and has not yet caught a real breach. Removing any single declaration brings back
exactly that one failure, so the declarations are precise rather than a blanket silence.

The lesson is narrower than (6) claimed and more useful: this repo records its reasons in
comments beside the queries, and a diagnosis made from the queries alone discards them.

**Files touched:** `ersatztv/main-hu.yml` (six `drift-ok` declarations and their explanation),
`scripts/check_watershed.py` (docstring and pass message), `docs/logs/changes-tracker.md`.

## 2026-11-18 (8) — What actually drops out: a shared-library blind spot, a stale inventory, and a capped genre field

Asked whether anything will drop out because of wrong filters, every source was counted live in
ErsatzTV and compared against the local model, and every Plex title was diffed against what
ErsatzTV imported.

**CORRECTION to (5)–(7): those model numbers ran against the October inventory.** The before/after
comparisons in (5) used `git checkout -- ersatztv/` twice. That also reverted the regenerated,
uncommitted `audit/library-inventory.csv` (5336 rows) to the October one (4224 rows, without The
New Looney Tunes, DuckTales, the Mézga shows or Little Mole), and only the `.yml` files were
restored. The model counts and watershed passes in (5)–(7), including "588 vs 593 agree", were
computed against that stale file. The inventory was regenerated and committed (`3e0389a`) and the
checks re-run: spot checks pass, `check_watershed.py` exits 0, and the only `[review]` rows are
the documented unrated titles in the trusted Cartoons and Documentaries libraries. Against the
current inventory every episode source agrees with live within 3%.

**Real drop-out, fixed: animated films were invisible to the main channels.** 32 files sit in
both the Plex `Movies` and `Animated` libraries. ErsatzTV imports a file once, and it filed all 32
under Animated, so ErsatzTV shows 868 Movies against Plex's 902. `MATINEE` and `AFTERNOON_FILM`
on `main.yml` and `main-hu.yml` searched `library_name:"Movies"` alone, while their comments say
"Animation stays in" and "animation kept". Toy Story, Shrek, The Lion King, Finding Nemo and
WALL·E could never air there. Both sources on both files now search Movies or Animated. Live:
main MATINEE 41 → 72, AFTERNOON_FILM 313 → 344; main-hu MATINEE 19 → 37, AFTERNOON_FILM
173 → 191. Watershed still passes. The kids and films channels already named both libraries.
The model still carries both rows per shared file, so it over-counts these sources by the
duplicates (MATINEE 88 modelled vs 72 live); that is the conservative direction.

**Not filter problems, and not losses:**
- Glass Tiger and Glass Tiger 2 were added to Plex at 05:41 today, after ErsatzTV's last sync.
- Grey's Anatomy S10E01E02 and the two Miami Vice double pilots are one file with two Plex
  entries; ErsatzTV imports the file once and it airs whole.
- MegaStructures and Planet Earth count high live because `show_title:` is a phrase match
  ("Planet Earth" also matches "Planet Earth II").

**Needs a re-sync in ErsatzTV (user action):** The Mézga Family. Plex renamed it from "A Mézga
család" on 16 Nov; ErsatzTV still has the old title and 13 of the 39 episodes. No schedule
names the show (CARTOONS takes the whole library), so the title is harmless; the 26 missing
episodes are not. A Cartoons sync, and a Movies sync for Glass Tiger, should bring both in.

**Model blind spot found, not yet fixed: the inventory caps genres at two.** Plex's list endpoint
returns only the first two genres per item, so 858 of 902 films show exactly two in the CSV; full
metadata has more (48 Hrs. is also crime, drama and thriller). ErsatzTV indexes the full set, so
live genre sources run larger than modelled (PRIME_DRAMA 654 vs 481, NATURE 257 vs 144). This
cannot add films above a ceiling: every gated film source also carries a rating allow-list, which
applies to every film it matches. `NOT genre:horror` exclusions err the safe way, because the
model keeps films that live drops. The cost is that genre-selected films outside the model are
never individually examined. The fix is a per-item metadata fetch in the audit (about 1,000
requests).

**Drop-outs by data, by design:** the Hungarian channels need `language_tag:hu*`, so Hungarian
audio without a language tag never airs there; the 2 genreless films can't reach genre sources;
unrated films air only after 22:00 (fail-closed).

**Files touched:** `ersatztv/main.yml`, `ersatztv/main-hu.yml` (MATINEE and AFTERNOON_FILM scope
plus a comment on why), `docs/logs/changes-tracker.md`.

## 2026-11-18 (9) — ErsatzTV UI changes made by the agent, at the user's request

The repo's posture is analysis-only, and the ErsatzTV web UI had been used read-only. The user
explicitly authorised UI changes on ErsatzTV (port 8409 on the Plex host) for this setup:
FFmpeg profile, channels and playouts. Nothing else on the network was touched; the schedule
deploy stays a user step because it needs SSH to the Plex host.

**FFmpeg profile 1**, renamed `1080p VAAPI h264 aac`: Hardware Acceleration VAAPI, driver
RadeonSI, display drm, device `/dev/dri/renderD129` (the only device offered), video 8000 kbit/s
with a 16000 kbit buffer. Everything else left at its default.

**Default channel `1 - ErsatzTV` deleted**, as the user chose, to free number 1.

**Streaming engine: Next, not Legacy, which reverses the earlier plan.** Choosing Legacy on the
channel form shows: "The legacy streaming engine will be removed in ErsatzTV 26.12." Channels
built on Legacy now would need migrating at the next release, so the six channels use Next with
Streaming Mode MPEG-TS. The earlier "test Next on one channel" step therefore becomes the main
setup. If a channel misbehaves on Next, the warning asks for a report via Troubleshooting →
Upload Results.

**Channels not yet created.** Stream Selector Mode Custom lists only "(none)" because the selector
files are not on the host yet, and playouts need the schedule files. Waiting for
`scripts/deploy_ersatztv.sh`, after which: six channels (1–3 English with `stream-selector-en.yml`,
4–6 Hungarian with `stream-selector-hu.yml`), six Sequential playouts, then a check of the XMLTV.

## 2026-11-18 (10) — Six channels and six playouts live; the container is still on UTC

The user deployed via Proxmox (`pct push`; the LXC has no SSH). All eight files on disk match
the repo md5 for md5.

Created in the ErsatzTV UI: channels 1 Main, 2 Kids & Family, 3 Movies (Custom selector
`stream-selector-en.yml`) and 4 Main HU, 5 Kids & Family HU, 6 Movies HU (`stream-selector-hu.yml`),
all Next engine, MPEG-TS, profile `1080p VAAPI h264 aac`. Six Sequential playouts point at
`/config/sequential-schedules/<file>.yml`. None was flagged as a failed build.

The XMLTV shows all six channels with about 55 hours of guide and no gap over a minute.

**But every daypart runs an hour late.** The XMLTV times carry `+0000`, and Main's 06:00 start
appears as 06:00 UTC, which is 07:00 in Budapest; Movies' 09:00 start comes out at 10:00. The
ErsatzTV log timestamps are UTC as well: the 05:12 library sync is logged at 04:12. The 2026-11-18
(3) TZ fix was never confirmed inside the container. The age ladder still holds an hour late,
and the cut-offs only move later, so nothing airs earlier than intended. Fix: set
`TZ=Europe/Budapest` in the compose file, recreate the container, then Reset All Playouts.

## 2026-11-18 (11) — Container timezone fixed; two films Plex never analysed

The compose file said `TZ=Etc/UTC`, not `TZ=UTC`, so the morning's `sed` (which matched only
`TZ=UTC`) silently changed nothing. The user replaced the line with `TZ=Europe/Budapest` and
recreated the container; `docker exec ersatztv date` now prints CET. Reset All Playouts ran from
the UI. The XMLTV now carries `+0100`, every channel has a full guide with no gaps, and the
dayparts land on local time (Main's 14:00 looser mix, Kids & Family's 15:00 family shows and
18:00 feature).

The installer's UTC warning had the same blind spot: it compared only against `UTC`. It now
treats `Etc/UTC` and the other UTC aliases (UCT, Universal, Zulu, GMT) as UTC.

**Zero-duration health check** (Oceans in Glass, Contact 1997): the files are intact by size
(300 MB and 5 GB), but Plex has no media analysis for either. Each has a catalogue running time
but no measured duration, container or codec. ErsatzTV takes duration from Plex's analysis, so it
records 0, and a zero-length item cannot be scheduled. Fix: Analyze both in Plex, then sync the
library in ErsatzTV. If Plex's analysis fails, run ffprobe inside the container to show whether
the file itself is damaged.

## 2026-11-18 (12) — Plex DVR re-added and working; the two zero-duration files are unreadable

The old Plex DVR pointed at the previous install's tuner and could not read it. The user deleted
it and re-added: DVR 4, ErsatzTV tuner `alive`/enabled, XMLTV guide, six channel mappings,
C1…C6 to 1…6. Plex's log shows the guide loading four times between 15:51 and 15:55, each in
about 3.5 s with "0 HTTP errors", and matching programmes to library items. The only failures
are the six channel logos (`/iptv/logos/gen`), which Plex's own asset fetcher aborts ("operation
aborted by pre-request callback", code 42). That is cosmetic: channels show without logos.

Plex Analyze on Contact (1997) and Oceans in Glass fails at 15:48–15:50 within 40 ms of opening
each file: "Invalid data found when processing input" / "Could not parse". Both files have the
expected size, but their contents are not readable media, so no tool can measure a duration and
ErsatzTV keeps them at zero. They need replacing; nothing on the ErsatzTV side can fix them.

## 2026-11-18 (13) — Stream settings audited against the library; live streams verified

**Library** (5215 playable items across the five scheduled libraries): 1080p 1557, 720p 1387,
SD/480/576 about 2000, 4K 274. H.264 3139, MPEG-4 1437, HEVC 545, a few MPEG-2, VC-1, AV1 and
one `drmi` (DRM-protected, unplayable). Frame rates: 24p 3137 and PAL 25 1963. About 2030 items
have 5.1 or 7.1 audio. HDR: 195 films and 59 TV episodes, including 12 Dolby Vision films with no
HDR10 base layer (No Time to Die, Gladiator II, Glass Onion, Alien: Romulus and others).

**GPU** (VAAPI tab of Troubleshooting): RadeonSI on `renderD129`, the Ryzen 5 7600X's integrated
Radeon (Raphael), Mesa 26.0.3. It decodes H.264, HEVC Main and Main10, VP9 profiles 0 and 2,
and AV1 profile 0, and encodes H.264 and HEVC.

**Live check**: 20 s captured from the MPEG-TS stream of channel 1 (Rocky, 4K HDR10, DTS-HD MA)
and channel 4 (Iron Man, 4K Dolby Vision, TrueHD 7.1). Both came out 1080p H.264 High, BT.709,
23.976 fps, stereo AAC 48 kHz, about 8.4 Mbit/s, starting within about 2 s. Frames show correct
SDR tone-mapping with no purple/green Dolby Vision cast, even though the profile's algorithm
reads "Linear". ErsatzTV logged no errors.

**Profile kept as is**: 1080p scale-and-pad, 8 Mbit/s, deinterlace on, frame-rate normalisation
off. If the Apple TV stutters at a switch between 24p and 25p programmes, turning frame-rate
normalisation on is the fix. The user declined loudness normalisation and 5.1 output for now.

**Changed, at the user's request**: global FFmpeg setting "Extract Embedded (Text) Subtitles"
turned on, so the selectors' English-subtitle rules can use text subtitles inside MKV files.
Confirmed on after a page reload.

## 2026-11-18 (14) — No multi-track passthrough; stream-copy test on channel 3; fallback slate bug

**Multi-track request**: the user wanted every audio and subtitle track to reach Plex so the
viewer can switch. Not possible with ErsatzTV feeding Plex Live TV, re-checked against the
release notes up to v26.12.0 / next v0.2.6. Both stream selectors pick one audio track; the
only all-audio mode (HLS Direct) is not usable by Plex and is removed in v26.12.0; MPEG-TS
carries no selectable subtitle track (v26.11.3). Plex shows "Unknown" because the single
output audio track carries no language tag. The EN and HU channels remain the way to choose.

**Changed in the ErsatzTV UI, at the user's request** (test on one channel only): new FFmpeg
profile 2 "1080p VAAPI copy (test)" with Normalize Video and Normalize Audio off, assigned to
channel 3 Movies. Other channels stay on profile 1. ErsatzTV forces Hardware Acceleration to
None while video copy is on, so items that cannot be copied (MPEG-4/AVI, burned-in subtitles,
DTS/TrueHD audio) are encoded on the CPU at 8 Mbit/s. To roll back, set channel 3's FFmpeg
Profile to "1080p VAAPI h264 aac".

**Bug found while testing**: channel 3 showed the error slate "playout item 1094 ended early".
With `Show Filler` on, the playout lists a single 7-minute Tom and Jerry short scheduled for
48:44 (21:11 to 22:00). `fallback` picks one item "to be looped and trimmed to exactly fit",
but next engine 0.2.4 plays it once and shows the slate for the rest of the gap. Over one page
per playout: Movies about 2.6 h a day of slate, Movies HU about 1.4 h, Main HU 20 min; Kids
gaps are short. Fixed upstream in v26.12.0 ("fallback error screen for the rest of a gap
after one clip ended early"). `scripts/install_ersatztv_plex_vm.sh` now pins
`ghcr.io/ersatztv/legacy:v26.12.0` (tag verified on ghcr). No schedule changes. The upgrade
is one-way and removes the legacy engine, which no channel uses.

## 2026-11-18 (15) — Upgraded to v26.12.0 (by the user); stream copy blocked by burned subtitles

Running v26.12.0 / next 0.2.5; all six channels kept their settings. Health checks: channel 3
flagged for not using hardware acceleration (expected with the copy profile), plus Contact and
Oceans in Glass (the latter now also missing from disk).

Channel 3 at 22:20 played Inglourious Basterds (4K HEVC, DTS) and logged "copy channel
transcodes item 1095: video (burned-in text subtitles); audio (dca is not in copy_formats)".
`stream-selector-en.yml` burns English subtitles in wherever they exist, and burning forces a
video transcode. Across 935 films in Movies and Animated (Plex metadata, the English or first
audio track): 916 have an English or untagged subtitle, so only 5 copy fully today. Without
the forced subtitles, 765 could copy video and 404 could copy both. Copyable audio: AC3 226,
EAC3 128, AAC 112, MP3 98; not copyable: DTS 284, TrueHD 72, FLAC 6, MP2 4.

**Subtitle rules confirmed by the user**: channels 1-3 play English audio with English
subtitles; channels 4-6 play Hungarian audio with no subtitles; other languages get English
subtitles on 1-3 and Hungarian on 4-6. Both selectors already do this. Known edge: a foreign
film that also has an English dub plays the dub, because English audio is preferred.

**Reverted, in the UI**: since English subtitles stay burned in, copy cannot help channel 3.
Channel 3 is back on profile 1 "1080p VAAPI h264 aac" (GPU). Profile 2 "1080p VAAPI copy
(test)" is left unused. The Streaming Engine field no longer exists in the channel editor.

## 2026-11-18 (16) — Poor picture on Apple TV traced to Plex; tuner set to Original format

User reported a soft picture with stalls on channels 1 and 3. Plex `/status/sessions` showed
720x404 at 1.46 Mbit/s, transcoding at speed 0.8. Two causes on the Plex side:
- Tuner device "ErsatzTV" had `transcodeProfile=heavy` ("Highest quality"), so the grabber
  fully re-encoded the incoming stream before the client transcode. **The user changed it to
  "Original format" (`none`).**
- The Apple TV requested `maxVideoBitrate=2000` with home quality at Maximum. After the
  tuner change and an app restart, requests no longer carry a bitrate cap.
Result: one transcode, 1920x1080 at about 20 Mbit/s, speed 1.5. Plex still refuses direct play
for live TV on the Apple TV ("live tv direct play is not allowed"), so one VAAPI re-encode
remains. ErsatzTV delivered faster than real time throughout (40 s in 34.7 s).

**Changed in the ErsatzTV UI, at the user's request**: profile 1 bitrate 8000 to 15000 kbit/s,
buffer 16000 to 30000. Verified on a freshly started channel 4 stream: 15.6 Mbit/s 1080p.

A leftover Plex tuner "ETV Multi-Audio Test" (on the Mac, port 5004) is still registered.

## 2026-11-19 (17) — Plex guide fixed; `fallback` replaced with top-up pads in all schedules

**Plex guide** spun forever on the Mac and Apple TV. Every `/lineups/dvr/channels` request
waited 15 s for `http://<mac>:5004/epg.xml` (the dead test tuner) and returned no
channels. Removing the tuner in the UI left its lineup on DVR 4 and the device registered.
The user removed both with HTTP DELETEs run from the Mac (lineup on `/livetv/dvrs/4/lineups`,
device `/media/grabbers/devices/6`). The guide now returns 6 channels in 0.04 s.

**LAN classification**: the Apple TV session reports `local: True`, `location: lan`. The
"(WAN)" tag in request log lines is only a label. Suggested setting LAN Networks to
the trusted and server VLAN subnets.

**Clock**: the Plex LXC (and so the Proxmox host) is 1 min 42 s slow against time.apple.com,
so programmes start that late. User to check `chronyc tracking` on Proxmox.

**Channel 3 "playout item failed to transcode"**: item 1102, a 7-minute Dexter's Laboratory
XviD MKV scheduled as `fallback` over 13:11-14:00. The user joined at 13:57; ffmpeg exited
with code 234 and the error card showed until 14:00. Not reproduced on channel 2's looped
Animaniacs gap, but that showed the other cost of `fallback`: one 22-minute episode played
about four times in a row over 12:37-14:10.

**Changed in the repo** (user chose whole shorts, blocks may start early): all 22 `fallback`
keys removed. Each is replaced by a second `pad_until` to the same time, `tomorrow: false`,
`trim: false`, `discard_attempts: 12`, drawing from the old fallback source (FILLER, or
SHORT_CARTOONS on the kids channels). Where the pad already drew from SHORT_CARTOONS (kids
20:30 and 07:00) the fallback is simply dropped. Blocks may now start a minute or two early.
`check_watershed.py` exits 0. Comments updated. Not yet deployed. Expected checksums:
main `beccba3901515fb15275282c49ffab44`, main-hu `9f65ce261a29afa3684cf6b718fe9c5a`,
kids `be34cac8f7579d342f8b0fbddf11ea7e`, kids-hu `8977a439de41d32f647f455aa7dc4698`,
movies `897bbd0a23dc7ac9e8de3d8cb44b7b9c`, movies-hu `6a7061a220802c8e9b9ce56853c1e3e4`.

## 2026-11-19 (18) — Plex library playback failing on the Apple TV (diagnosis only)

Red Eye and Send Help failed to play on the Apple TV. The client requested
`subtitles=burn` (plus `directPlay=0`, `directStream=0`, `boostDialog=1`), forcing a full
transcode. Plex's VAAPI transcode on the AMD iGPU (bundled driver) segfaulted (exit -11) on
all four attempts; the software retry still initialised VAAPI and failed ("Device creation
failed", exit 187). The user found the Apple TV app had subtitles set to always burn in and
changed it; playback works. The hardware-transcode crash remains latent: any library item
that does need a transcode (for example PGS subtitles) will still fail. Suggested test:
turn off "Use hardware acceleration when available" (decode), keep hardware encoding on.
No changes made by the agent.

## 2026-11-19 (19) — No gaps and no cartoon filler at daypart boundaries (supersedes the top-ups in 17)

User rule: no gaps and no cartoon filler. If a block ends 15 minutes or less before a boundary,
start the next block early. If the gap is longer, play another title from the earlier block,
preferably a short one, even though it runs into the next slot. Never a cartoon between two
adult films.

**Changed in the repo** (all six schedules, not yet deployed): every FILLER / SHORT_CARTOONS
top-up pad is gone, and so are the FILLER sources. Each boundary T is now a `pad_until` T that
fits whole items, then `pad_until` T minus 15 from the same block with `stop_before_end: false`.
That option is not in the ErsatzTV docs, but it is in the v26.12.0 model and schema. When it is
false, items are added until the target time is passed. A remainder of 15 minutes or less
makes the second pad a no-op, so the next block starts early. A longer remainder gets one more
item, which runs over T.
- **Main channels**: the overrun pads draw from the same mix as the block (10:00 to 22:00,
  seven boundaries).
- **Movie channels**: new FAMILY_SHORT and DAYTIME_SHORT sources (60–100 minutes). Live
  counts: 17 and 102 on movies, 9 and 62 on movies-hu. 22:00 overruns from SHORT_FILMS.
- **Day-start boundary** (06:00 main, 09:00 movies): the stricter morning block (CARTOONS,
  FAMILY_FILMS) starts early and pads to the start time exactly. Otherwise the
  `wait_until` after `repeat` would leave a shortfall off air.
- **Kids channels**: the overnight shorts pad loses `offline_tail` and gains
  `stop_before_end: false`, so there is no off-air tail before 07:00.

`scripts/check_watershed.py` now models a start up to 15 minutes early (EARLY_START) and the
overrun pads. It exits 0. All six files validate against ErsatzTV's
sequential-schedule.schema.json (v26.12.0). Expected checksums:
main `f08dd0d30ef155a8aebea1e46354bf5d`, main-hu `15a6fff0be73de9a22a43b01117043ab`,
kids `b35c031158c698cc36a0cd97c9d6165a`, kids-hu `ebc198dcf7b7cf07bff61025163ba36c`,
movies `9f63b39ed580b6f87239ff9caec59da6`, movies-hu `f3b16c835749dfbd5b4a4d3c94d9df19`.

## 2026-11-20 — Moved out of HA into its own repo

The TV station had outgrown the HA repo. HA PR #52 had already removed it from HA `main` and
archived it on the `ersatztv-archive` branch. This repo was created from that branch at
4d41664: all of `ersatztv/`, nine scripts (the checkers, counters, audits, deploy and install
scripts, and the Kometa installer), and the 70 TV entries from HA's changes tracker. The
schedule checksums are unchanged from entry (19). `check_watershed.py` passes from here.

It lives at `station/` inside the user's ErsatzTV source clone. The clone's git hides it with
`.git/info/exclude`, so it never mixes with upstream code or the clone's `multi-audio` work.
The name is `station/` and not `ersatztv/` because macOS treats `ersatztv` and the clone's
`ErsatzTV/` as the same folder. HA's guard hook was copied unchanged to the clone's
`.cursor/`, which is also excluded.

Still pending, unchanged by the move: the user deploying the six schedules from (19),
removing the dead Mac tuner (Plex device 7 and its lineup), and fixing the Plex container's
full disk (the transcoder cache).

## 2026-11-21 — Published on GitHub; `Animania` s01e03 found truncated

**Published** as the public repo `rbhun/ersatztv-legacy-improve`, as one fresh commit. Before
publishing, LAN addresses were replaced: the audit scripts default to `http://plex.internal:32400`
(override with `--url`), and the log names hosts instead of addresses. `ersatztv/audit/` is now
gitignored because it lists the whole library by release file name; regenerate it locally with
`plex_library_audit.py`. The earlier two-commit history, which still contains the addresses
and the audit files, is kept on the local-only branch `local-history`. Do not push it.

**Channel 5, 08:57:30–10:29:44**: "playout item … ended early" on *Animaniacs: Nighty-Night
Toon*. That item is `Animania - s01e03.avi`, one of three Hungarian-dubbed XviD compilations
(512×384) that Plex files as a second "Animaniacs" show with single-episode titles. Its header
says 1:32:14 (and 153,197 frames, about 1:42), but the video ends at 1:30:33 at a corrupt
packet, so the last ~1 min 40 s of the slot went to the fallback screen. s01e01 and s01e02
read cleanly to their ends (1:43:09 and 1:43:08). User to replace or delete s01e03; optional
follow-up is a length cap on the kids channels' cartoon sources.

## 2026-11-22 — Deploy from GitHub with a local overlay

Added `deploy/`: the ErsatzTV host pulls this public repo (and the public Legacy/Next forks),
builds or pulls the fork image, then merges schedules through `/opt/ersatztv/local/` so personal
overrides survive updates. `bootstrap.sh` wires `/opt/ersatztv-deploy` + `/opt/ersatztv/local`;
`ersatztv-update` is the everyday entry point. No LAN addresses or tokens in the new files.

## 2026-11-22 (2) — Single public repo for all improvements

Deploy no longer depends on separate `rbhun/ersatztv` / `rbhun/ersatztv-next` forks. Code
improvements live as `patches/legacy` and `patches/next` against the upstream tags in
`versions.env`. The target clones official upstream, applies the patches, and builds. Station
schedules, deploy scripts, and patches are one public repo; personal overlays stay in
`/opt/ersatztv/local/`.

## 2026-11-22 (3) — Health Check update UI + host agent

Added `deploy/target/update-agent.py` and a systemd unit so the ErsatzTV Health Checks
page can poll for updates every 10s, select a configured repo/branch, and trigger
`update.sh`. Updates backup and restore `/opt/ersatztv/local` (and re-apply the overlay)
so personal schedules/env survive. New legacy patch 0003 adds the UI client.

## 2026-11-22 (4) — Performance page statistics for Next channels

The System → Performance page showed "not available" for every channel, because they all
stream through the Next engine, which runs ffmpeg itself. New next patch 0002 runs ffmpeg
with `-progress pipe:1` and writes the latest report, with the item id, ffmpeg pid, output
start time and ffmpeg arguments, to `ffmpeg-progress.txt` in the channel folder. New legacy
patch 0008 reads that file, so Next channels now show speed, dropped/duplicated frames,
bitrate, resolution, frame rate, hardware decode/encode, CPU and buffer ahead of live.
Both full series apply on `LEGACY_TAG` / `NEXT_TAG`, build, and pass their tests.

## 2026-11-22 (5) — Performance page fixes for Next channels

First live look at a Next channel (VAAPI profile) showed a blank buffer and bitrate, the encoder
as "Software / unknown", no GPU filters, and a false 0.50x slowest speed. Next patch 0004 adds
the output frame rate and each report's wall clock time to `ffmpeg-progress.txt`. Legacy patch
0011 reads Next's `-vcodec` and every `-filter_complex` (Next adds one for extra audio), falls
back to that frame rate when there is no `-r` (fixes the buffer), times speed by the report
time instead of when the page read it, and measures bitrate from the HLS segment files, since
ffmpeg reports no size for the hls muxer.

## 2026-11-22 (6) — Underrun log

Legacy patch 0012 adds an underrun log to System → Performance. A background service checks
every streaming channel once a second, whether or not the page is open. An underrun starts
when the buffer ahead of live reaches zero (after a 30 s grace period at session start) and
ends when it is back above 2 s, so one stall is logged once. Each underrun records duration,
lowest buffer, slowest speed, item, realtime/work-ahead, hardware decode/encode and CPU. It is
logged as a warning, appended to `underruns.jsonl` in the logs folder (rotated at 5 MB), and the
page shows counts and stalled time for the last 24 hours and 7 days, per channel.
