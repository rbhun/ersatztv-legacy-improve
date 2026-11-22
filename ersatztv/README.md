# ErsatzTV channel schedules

Sequential Schedule definitions for the ErsatzTV instance that runs alongside Plex on port
8409, installed by `scripts/install_ersatztv_plex_vm.sh`. Since 2026-11 that host is an LXC
with an AMD iGPU rather than a VM, and transcoding is hardware-accelerated through VAAPI.

Six channels — three in English, three restricted to Hungarian audio — each a dayparted
broadcast day rather than a shuffle:

| File | Channel | Shape |
|---|---|---|
| `main.yml` | Main | Cartoons 06:00, daytime mix 10:00, looser mix 14:00, broad mix 18:00, feature 20:00, night mix 22:00, late films 00:00 |
| `main-hu.yml` | Main HU | Same shape, every source filtered to `language_tag:hu*` bar the cartoons |
| `kids.yml` | Kids & Family | Cartoons 07:00, family shows 15:00, feature 18:00, shorts 20:30, nature 21:00, dark |
| `kids-hu.yml` | Kids & Family HU | Same shape; cartoons and family shows deliberately unfiltered |
| `movies.yml` | Movies | Family films 09:00, daytime films 14:00, comedy 18:00, five unrestricted films from 22:00 |
| `movies-hu.yml` | Movies HU | Same shape, dubbed only |

Plus two stream selectors, `stream-selector-en.yml` and `stream-selector-hu.yml`, which choose
the audio and subtitle track *inside* a file. They cannot filter the catalogue — that is why
the HU channels need their own schedule files rather than just a different selector.

### The age ladder

Enforced across all six channels and machine-checked by `scripts/check_watershed.py`:

| Window | Ceiling |
|---|---|
| 06:00–14:00 | nothing 12+ |
| 14:00–18:00 | nothing 16+ |
| 18:00–22:00 | nothing 18+ |
| 22:00–06:00 | anything |

The two children's channels hold the under-12 ceiling all day instead of stepping up.

Every tier is an **allow-list, never an exclusion**, because `NOT content_rating:"hu/18"` is
true for an item with no rating and this library contains unrated adult material. An allow-list
fails closed: unknown means excluded, so unknown airs after 22:00 only. The two exceptions are
the `Cartoons` and `Documentaries` libraries, which are trusted on curation because most of
their titles carry no rating at all; both are documented at the point of use.

Why Sequential Schedules rather than clicking through Blocks and Templates in the UI:
the programming is reviewable in a diff, version-controlled here, and queries can be
tuned in a text editor. The trade-off is that ErsatzTV's UI is then not the source of
truth for these channels — edit the files, not the UI.

## Deploying

Preferred path on the ErsatzTV host: pull this public repo and apply the local overlay
(see [`deploy/README.md`](../deploy/README.md)):

```bash
ersatztv-update --overlay
```

Site-specific schedule edits belong in `/opt/ersatztv/local/schedules/` so a git pull cannot
overwrite them. Public defaults stay in this folder.

From a laptop you can still push YAML over SSH:

```bash
scripts/deploy_ersatztv.sh user@host
```

Do not hand-roll `scp` and `cp` for this. On 2026-10-10 a hand-rolled deploy appeared to
succeed and did not — the transfer silently moved nothing, the follow-up copy installed stale
files from `/tmp`, and an hour went into chasing what looked like three separate ErsatzTV
bugs. The script compares md5 sums after copying and exits non-zero on any mismatch, which is
the whole reason it exists: a deploy that cannot fail loudly eventually fails quietly.

`/opt/ersatztv/config` on the host is `/config` inside the container, so the files are
visible to ErsatzTV immediately — no restart needed.

There are **two** target subfolders, not one:

| Repo file | Container path | Host path |
|---|---|---|
| the six schedule `.yml` files | `/config/sequential-schedules/` | `/opt/ersatztv/config/sequential-schedules/` |
| the two `stream-selector-*.yml` files | `/config/scripts/channel-stream-selectors/` | `/opt/ersatztv/config/scripts/channel-stream-selectors/` |

Verify a copy landed with `sudo docker exec ersatztv ls -l /config/sequential-schedules
/config/scripts/channel-stream-selectors` — check the timestamps actually moved.

### Copying the files is only the first of three steps

Schedules are resolved into playouts at build time, and Plex caches the guide on top of that,
so **three layers have to be cleared in order** or stale programmes keep appearing:

1. the files above — the source,
2. ErsatzTV: **Scheduling → Playouts → Reset All Playouts**, which re-resolves every query into
   concrete programmes and times,
3. Plex: the DVR's **Refresh Guide**, which re-reads the XMLTV ErsatzTV generates.

Skipping step 2 or 3 is what leaves deleted programme titles in the EPG long after the YAML is
correct. After step 2, open a playout and confirm it lists concrete programmes with times — **an
empty playout means a query matched nothing**, and ErsatzTV highlights failed builds in yellow.

## Wiring a channel

Per channel, in the UI:

1. **Channels → Add Channel.** Any free number, a name, and a **Group** (Plex uses the
   group for guide categorization). Set **Streaming Mode** to **MPEG-TS** — that's the
   mode built for clients wanting an HDHomeRun-style tuner, which is what Plex Live TV
   is. Upload a logo; it shows in the Plex guide.
2. **Playouts → Add Playout.** Pick the channel, choose the **Sequential** schedule kind,
   and select the matching `.yml`. Saving triggers the playout build.
3. Open the playout and confirm it lists concrete programmes with times. **An empty
   playout means a query matched nothing** — fix the query, not the channel.

## Tuning the queries

Regenerate the evidence any time with `python3 scripts/plex_library_audit.py`, which writes
`audit/library-audit.txt` and `audit/library-inventory.csv`. What the first audit found:

**Always scope by `library_name`.** Plex types two junk libraries as movies — `Demos`
(2 LG 4K demo loops) and `Other videos` (42 drone clips, GoPro files, Zoom recordings,
home video). An unscoped `type:movie` query sweeps them in. Worse, 40 of those 42 carry no
genre, and `NOT genre:animation` is **true** for an item with no genre at all, so an
exclusion-style query actively selects them. That is how holiday drone footage ends up in
prime time. Every query in these files is library-scoped for this reason.

**Do not select children's content by genre.** `genre:animation` on episodes matches
**Archer** (animation|comedy, 75 episodes) in the TV Series library. `genre:family` pulls
7th Heaven (199 eps) and the Planet Earth documentaries. The Kids channel therefore selects
by `library_name:"Cartoons"`, which uses the separation already curated in Plex — and as a
bonus reaches the 25 episodes of *Me and Winnie the Pooh*, whose show carries no genre and
which no genre query can see. Keep the Cartoons library clean and the channel stays safe.

**Content ratings are Hungarian.** Measured: `hu/16` (257), `hu/12` (210), `hu/18` (136),
`hu/KN` (17), `hu/6` (8), `hu/14` (6), with a US-style minority (`R` 37, `PG-13` 30, `PG`
15, `G` 12). So `content_rating:"PG"` would match 15 of 786 films. Ratings are left out of
these files; `hu/KN` and `hu/6` are the child-safe values, and `NOT content_rating:"hu/18"`
is the lever for keeping the strongest material out of a daypart.

**Episodes have no `genre` field — use `show_genre`.** This is the easiest mistake to make
and it fails silently. ErsatzTV's episode index exposes `show_genre`, `show_title`,
`show_studio`, `show_network`, `show_content_rating` and `show_tag`, but **not** `genre`. A
query of `type:episode AND genre:comedy` matches nothing at all. Movie queries do use
`genre:`. The same applies to `content_rating`, which for episodes is `show_content_rating` —
that one is used here as a `NOT show_content_rating:"TV-MA"` fail-safe on every family
source, so a mis-tagged adult show cannot reach the Kids channel even if library hygiene
slips.

**`tag:` does not work with Plex metadata** at all. Most community examples online lean on
it and will silently match nothing here.

**Genres live on the movie and on the show, never on the episode.** So one unlabelled show
takes all of its episodes with it, which is why the audit reports blocked episode counts.

**Ratings are not queryable.** ErsatzTV indexes no critic, audience, or personal score.
Plex has them with good coverage (audience on 98% of films, critic on 90%), so the way in is
a Plex smart collection filtered by rating, matched here with `collection:"Name"` — see the
worked recipe at the bottom of `movies.yml`.

Always paste a query into the ErsatzTV **Search** box and confirm the count before
committing it here.

## Library reality

| Library | Type | Items | Notes |
|---|---|---|---|
| Movies | movie | 786 | 775 carry a genre; 11 do not |
| TV Series | show | 42 | 2545 episodes |
| Cartoons | show | 6 | 422 episodes — cycles in about a week |
| Animated | movie | 4 | tiny; 1 has no genre |
| Other videos | movie | 42 | **junk** — home video, must stay excluded |
| Demos | movie | 2 | **junk** — LG demo loops |

Eleven real films in the Movies library carry no genre and so cannot be reached by any
query: *9*, *A tanu*, *All That Jazz*, *Bottle Rocket*, *Gia*, *Home*, *Robin Hood (2010)*,
*The Beach*, *Imax Extreme Adventure Grand Canyon*, and two raw release names that never
matched. Because `FEATURE_FILM` in `main.yml` is an exclusion query scoped to the Movies
library, those genreless films **do** still air there — but they are invisible to every
genre-specific daypart. Fixing their metadata in Plex adds them to the rotation
automatically.

## Known trade-off: dayparts start early rather than clipping

Every `pad_until` is `trim: false`, so programmes always play whole. Nothing is cut
mid-scene. The cost is paid at the other end: when the remaining gap is shorter than
anything the pool can offer, that time goes unused and **the next instruction starts early**.

`main.yml` and `main-hu.yml` keep a `fallback` on only two of their pads — the 10:00 cartoon
block and the overnight 06:00 pad. The six daypart fallbacks were deliberately removed on
2026-10-17. With a fallback in place, ErsatzTV loops short filler to hold the clock, but it
also hides that filler from XMLTV by stretching the previous programme's stop time over it,
which produced a guide claiming minutes that no longer existed and an unannounced cartoon
playing over them. Dropping the fallback trades that for an early start.

The exposure is worth stating plainly, because an early start can cross a watershed: the film
scheduled for 22:00 may begin a few minutes before 22:00, and the gap is bounded only by the
shortest item the pool can offer. If that ever matters more than the interruption,
each affected pad carries a comment showing the `fallback: "EVENING_MIX"` form, which holds
the clock with rating-appropriate content at the cost of one truncated episode.

`kids.yml` and `kids-hu.yml` take the other route: every pad has `fallback: "SHORT_CARTOONS"`,
drawing on 271 shorts of 3 to 9 minutes, which is exactly the short-filler content that makes
a fallback work properly. `movies.yml` uses `count` so films always play whole, accepting
drift from the nominal times.

## Capacity

Channel count is nearly free — an idle channel runs no FFmpeg process. Cost scales with
**concurrent viewers**, not channels.

Since 2026-11 transcoding is hardware-accelerated. ErsatzTV runs in the same LXC as Plex,
which has an AMD iGPU passed in, so the FFmpeg profile uses **VAAPI**. The RTX A2000 remains
passed through to the LLM VM and GPU policy still ranks LLM first — this is the iGPU, not that
card, so there is no contention between the two. CPU load and therefore fan noise under the
host's deliberate `powersave` governor is far lower than the CPU-only arrangement it replaced.

The render node is **not** `renderD128` on this host. The LXC is passed one node, which
enumerates as `/dev/dri/renderD129`, and ffmpeg's own default is `renderD128` — so the FFmpeg
profile has to name the device explicitly or hardware encoding fails at playback despite a
correct install. Verify the chain end to end with:

```bash
docker exec ersatztv ffmpeg -hide_banner -loglevel error \
  -init_hw_device vaapi=va:/dev/dri/renderD129 \
  -f lavfi -i testsrc=d=1:s=1280x720 \
  -vf 'format=nv12,hwupload' -c:v h264_vaapi -f null - && echo "VAAPI ENCODE OK"
```
