#!/usr/bin/env python3
"""Host-side update agent for ErsatzTV Health Check UI.

Listens on UPDATE_AGENT_BIND (default 0.0.0.0:8410). The container reaches it via
host.docker.internal. All mutating calls require header X-Update-Token matching
UPDATE_AGENT_TOKEN in /opt/ersatztv/local/env.

Endpoints:
  GET  /                 HTML progress page (no auth — stays up while ETV is down)
  GET  /v1/sources
  GET  /v1/check?source=<id>
  GET  /v1/status
  GET  /v1/log
  POST /v1/update?source=<id>   JSON {"source":"<id>"} (query or body)

API routes still require X-Update-Token. The HTML page is intentionally open on
the LAN so you can watch a rebuild after ErsatzTV has been stopped.
"""
from __future__ import annotations

import html
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ETV_DIR = Path(os.environ.get("ETV_DIR", "/opt/ersatztv"))
LOCAL_ENV = ETV_DIR / "local" / "env"
DEPLOY_DIR = Path(os.environ.get("DEPLOY_DIR", "/opt/ersatztv-deploy"))
LOG_PATH = ETV_DIR / "update-agent.log"
STATE_LOCK = threading.Lock()
STATE = {
    "updating": False,
    "lastStarted": None,
    "lastFinished": None,
    "lastOk": None,
    "lastError": None,
    "lastSource": None,
}


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if not LOCAL_ENV.is_file():
        return env
    for line in LOCAL_ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        env[key.strip()] = val.strip().strip("'").strip('"')
    return env


def parse_sources(env: dict[str, str]) -> list[dict[str, str]]:
    # Format: id|Label|git-url|branch ; id2|Label2|url|branch
    raw = env.get(
        "UPDATE_SOURCES",
        "improvements|Improvements|https://github.com/rbhun/ersatztv-legacy-improve.git|main",
    )
    sources = []
    for part in raw.split(";"):
        part = part.strip()
        if not part:
            continue
        bits = [b.strip() for b in part.split("|")]
        if len(bits) != 4:
            continue
        sid, label, url, branch = bits
        sources.append({"id": sid, "label": label, "url": url, "branch": branch})
    return sources


def append_log(msg: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"[{stamp}] {msg}\n")
        fh.flush()


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run a command, streaming stdout/stderr into the agent log as they arrive."""
    # Force line-buffered child output when possible (dotnet/docker otherwise stall).
    if shutil.which("stdbuf") and cmd and cmd[0] != "stdbuf":
        cmd = ["stdbuf", "-oL", "-eL", *cmd]
    append_log("$ " + " ".join(cmd))
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        env=env,
    )
    assert proc.stdout is not None
    collected: list[str] = []
    for line in proc.stdout:
        text = line.rstrip("\n")
        collected.append(text)
        append_log(text)
    returncode = proc.wait()
    return subprocess.CompletedProcess(cmd, returncode, "\n".join(collected), "")


def tail_log(n: int = 120) -> str:
    if not LOG_PATH.is_file():
        return ""
    lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-n:]) + ("\n" if lines else "")


def progress_html() -> str:
    with STATE_LOCK:
        state = dict(STATE)
    updating = bool(state.get("updating"))
    last_ok = state.get("lastOk")
    if updating:
        badge = "UPDATING"
        badge_color = "#b45309"
    elif last_ok is True:
        badge = "OK"
        badge_color = "#15803d"
    elif last_ok is False:
        badge = "FAILED"
        badge_color = "#b91c1c"
    else:
        badge = "IDLE"
        badge_color = "#475569"

    def fmt_ts(value: object) -> str:
        if not value:
            return "—"
        try:
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(value)))
        except (TypeError, ValueError, OSError):
            return str(value)

    version = installed_version() or "—"
    head = git_head(DEPLOY_DIR) or "—"
    log_text = html.escape(tail_log(150))
    err = html.escape(str(state.get("lastError") or ""))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta http-equiv="refresh" content="2"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>ErsatzTV update</title>
  <style>
    :root {{ color-scheme: light dark; font-family: ui-sans-serif, system-ui, sans-serif; }}
    body {{ margin: 0; padding: 1.25rem; background: #0f172a; color: #e2e8f0; }}
    h1 {{ font-size: 1.25rem; margin: 0 0 0.75rem; }}
    .row {{ display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: center; margin-bottom: 1rem; }}
    .badge {{ background: {badge_color}; color: #fff; padding: 0.25rem 0.6rem; border-radius: 999px; font-weight: 700; letter-spacing: 0.04em; }}
    .meta {{ color: #94a3b8; font-size: 0.9rem; }}
    .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 0.75rem; padding: 1rem; }}
    pre {{ margin: 0; white-space: pre-wrap; word-break: break-word; font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace; max-height: 70vh; overflow: auto; }}
    .err {{ color: #fca5a5; margin-top: 0.75rem; }}
  </style>
</head>
<body>
  <h1>ErsatzTV update agent</h1>
  <div class="row">
    <span class="badge">{badge}</span>
    <span class="meta">source: {html.escape(str(state.get("lastSource") or "—"))}</span>
    <span class="meta">started: {fmt_ts(state.get("lastStarted"))}</span>
    <span class="meta">finished: {fmt_ts(state.get("lastFinished"))}</span>
  </div>
  <div class="row meta">
    <span>installed: {html.escape(version)}</span>
    <span>deploy HEAD: {html.escape(head[:12] if head != "—" else head)}</span>
    <span>auto-refresh 2s · this page stays up while ErsatzTV is stopped</span>
  </div>
  {"<div class='err'>last error: " + err + "</div>" if err else ""}
  <div class="card"><pre id="log">{log_text}</pre></div>
  <script>
    const log = document.getElementById('log');
    if (log) log.scrollTop = log.scrollHeight;
  </script>
</body>
</html>
"""


def git_head(repo: Path) -> str | None:
    if not (repo / ".git").exists():
        return None
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def git_remote_sha(url: str, branch: str) -> str | None:
    proc = subprocess.run(
        ["git", "ls-remote", url, f"refs/heads/{branch}"],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return proc.stdout.split()[0]


def installed_version() -> str | None:
    path = ETV_DIR / ".build-cache" / "last-version"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return None


def ensure_local(env: dict[str, str]) -> None:
    """Create local overlay scaffolding without clobbering existing personal files."""
    example = DEPLOY_DIR / "deploy" / "local.example"
    local = ETV_DIR / "local"
    local.mkdir(parents=True, exist_ok=True)
    for sub in ("schedules", "stream-selectors", "graphics"):
        (local / sub).mkdir(parents=True, exist_ok=True)
    if not (local / "env").is_file():
        if (example / "env").is_file():
            shutil.copy2(example / "env", local / "env")
            append_log("created local/env from example")
        else:
            append_log("warning: no local/env and no example to copy")
    if example.is_dir():
        for name in ("README.md",):
            src = example / name
            dst = local / name
            if src.is_file() and not dst.exists():
                shutil.copy2(src, dst)


def backup_local() -> Path:
    backup = ETV_DIR / ".local-backup"
    if backup.exists():
        shutil.rmtree(backup)
    backup.mkdir(parents=True)
    local = ETV_DIR / "local"
    if local.exists():
        shutil.copytree(local, backup / "local", dirs_exist_ok=True)
        append_log(f"backed up local overlay to {backup / 'local'}")
    # Preserve live config schedules that may have been hand-edited outside git.
    live_sched = ETV_DIR / "config" / "sequential-schedules"
    if live_sched.is_dir():
        shutil.copytree(live_sched, backup / "sequential-schedules", dirs_exist_ok=True)
        append_log("backed up live sequential-schedules")
    live_sel = ETV_DIR / "config" / "scripts" / "channel-stream-selectors"
    if live_sel.is_dir():
        shutil.copytree(live_sel, backup / "channel-stream-selectors", dirs_exist_ok=True)
        append_log("backed up live stream selectors")
    return backup


def restore_local(backup: Path) -> None:
    """Re-apply personal overlay files after update (never touch the SQLite DB)."""
    src = backup / "local"
    if not src.is_dir():
        return
    dest = ETV_DIR / "local"
    dest.mkdir(parents=True, exist_ok=True)
    for path in src.rglob("*"):
        if path.is_dir():
            continue
        rel = path.relative_to(src)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    append_log("restored local overlay from backup")


def switch_source(source: dict[str, str]) -> None:
    if not DEPLOY_DIR.exists():
        append_log(f"cloning {source['url']} -> {DEPLOY_DIR}")
        DEPLOY_DIR.parent.mkdir(parents=True, exist_ok=True)
        proc = run(["git", "clone", "--branch", source["branch"], source["url"], str(DEPLOY_DIR)])
        if proc.returncode != 0:
            raise RuntimeError("git clone failed")
        return
    run(["git", "-C", str(DEPLOY_DIR), "remote", "set-url", "origin", source["url"]])
    run(["git", "-C", str(DEPLOY_DIR), "fetch", "origin", source["branch"]])
    proc = run(
        [
            "git",
            "-C",
            str(DEPLOY_DIR),
            "checkout",
            "-B",
            source["branch"],
            f"origin/{source['branch']}",
        ]
    )
    if proc.returncode != 0:
        raise RuntimeError("git checkout failed")


def run_update(source_id: str) -> None:
    env = load_env()
    sources = {s["id"]: s for s in parse_sources(env)}
    if source_id not in sources:
        raise RuntimeError(f"unknown source {source_id}")
    source = sources[source_id]

    with STATE_LOCK:
        if STATE["updating"]:
            raise RuntimeError("update already in progress")
        STATE["updating"] = True
        STATE["lastStarted"] = time.time()
        STATE["lastSource"] = source_id
        STATE["lastError"] = None

    try:
        append_log(f"=== update start source={source_id} ===")
        ensure_local(env)
        backup = backup_local()
        switch_source(source)
        # Re-ensure after pull: new example files may appear; never overwrite env.
        ensure_local(load_env())
        update_sh = DEPLOY_DIR / "deploy" / "target" / "update.sh"
        if not update_sh.is_file():
            raise RuntimeError(f"missing {update_sh}")
        # --no-pull: we already fetched/checked out the selected source.
        proc = run(["bash", str(update_sh), "--no-pull"], cwd=DEPLOY_DIR / "deploy" / "target")
        restore_local(backup)
        # Re-apply overlay so restored local schedules win again.
        apply = DEPLOY_DIR / "deploy" / "target" / "apply-overlay.sh"
        if apply.is_file():
            run(["bash", str(apply)], cwd=apply.parent)
        if proc.returncode != 0:
            raise RuntimeError(f"update.sh exited {proc.returncode}")
        with STATE_LOCK:
            STATE["lastOk"] = True
            STATE["lastFinished"] = time.time()
        append_log("=== update ok ===")
    except Exception as exc:  # noqa: BLE001
        with STATE_LOCK:
            STATE["lastOk"] = False
            STATE["lastError"] = str(exc)
            STATE["lastFinished"] = time.time()
        append_log(f"=== update failed: {exc} ===")
        raise
    finally:
        with STATE_LOCK:
            STATE["updating"] = False


class Handler(BaseHTTPRequestHandler):
    server_version = "ErsatzTVUpdateAgent/1.0"

    def _env(self) -> dict[str, str]:
        return load_env()

    def _authorized(self) -> bool:
        env = self._env()
        expected = env.get("UPDATE_AGENT_TOKEN", "")
        if not expected:
            # Refuse rather than run open.
            return False
        got = self.headers.get("X-Update-Token", "")
        return got == expected

    def _json(self, code: int, payload: object) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _text(self, code: int, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_chunked(self) -> bytes:
        chunks: list[bytes] = []
        while True:
            line = self.rfile.readline()
            if not line:
                break
            size_token = line.split(b";", 1)[0].strip()
            try:
                size = int(size_token, 16)
            except ValueError:
                break
            if size == 0:
                # Trailer + final CRLF
                while True:
                    trailer = self.rfile.readline()
                    if trailer in (b"\r\n", b"\n", b""):
                        break
                break
            chunks.append(self.rfile.read(size))
            self.rfile.readline()  # chunk CRLF
        return b"".join(chunks)

    def _read_json(self) -> dict:
        length_hdr = self.headers.get("Content-Length")
        te = (self.headers.get("Transfer-Encoding") or "").lower()
        try:
            if length_hdr not in (None, ""):
                length = int(length_hdr)
                raw = self.rfile.read(length) if length > 0 else b"{}"
            elif "chunked" in te:
                raw = self._read_chunked() or b"{}"
            else:
                raw = b"{}"
            return json.loads(raw.decode("utf-8") or "{}")
        except Exception as exc:  # noqa: BLE001
            append_log(f"failed to parse update JSON body: {exc}")
            return {}

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        # Public progress UI — independent of the ErsatzTV container.
        if path in ("/", "/progress", "/status"):
            body = progress_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/v1/sources":
            if not self._authorized():
                return self._json(401, {"error": "unauthorized"})
            return self._json(200, {"sources": parse_sources(self._env())})

        if path == "/v1/status":
            if not self._authorized():
                return self._json(401, {"error": "unauthorized"})
            with STATE_LOCK:
                status = dict(STATE)
            status["installedVersion"] = installed_version()
            status["localHead"] = git_head(DEPLOY_DIR)
            status["deployDir"] = str(DEPLOY_DIR)
            return self._json(200, status)

        if path == "/v1/check":
            if not self._authorized():
                return self._json(401, {"error": "unauthorized"})
            source_id = (qs.get("source") or [None])[0]
            sources = {s["id"]: s for s in parse_sources(self._env())}
            if not source_id or source_id not in sources:
                return self._json(400, {"error": "unknown source"})
            source = sources[source_id]
            local = git_head(DEPLOY_DIR)
            remote = git_remote_sha(source["url"], source["branch"])
            update_available = bool(remote and local and remote != local) or bool(remote and not local)
            return self._json(
                200,
                {
                    "source": source,
                    "localSha": local,
                    "remoteSha": remote,
                    "updateAvailable": update_available,
                    "installedVersion": installed_version(),
                    "checkedAt": time.time(),
                },
            )

        if path == "/v1/log":
            if not self._authorized():
                return self._json(401, {"error": "unauthorized"})
            return self._text(200, tail_log(200))

        return self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/v1/update":
            return self._json(404, {"error": "not found"})
        if not self._authorized():
            return self._json(401, {"error": "unauthorized"})
        qs = urllib.parse.parse_qs(parsed.query)
        body = self._read_json()
        # Prefer query string — some HttpClients send chunked JSON without a
        # Content-Length that BaseHTTPRequestHandler can read as a body.
        source_id = (qs.get("source") or [None])[0] or body.get("source")
        if not source_id:
            append_log(f"update rejected: source missing (query={dict(qs)} body={body})")
            return self._json(400, {"error": "source required"})

        def worker() -> None:
            try:
                run_update(source_id)
            except Exception:  # noqa: BLE001
                pass

        with STATE_LOCK:
            if STATE["updating"]:
                return self._json(409, {"error": "update already in progress"})
        threading.Thread(target=worker, daemon=True).start()
        return self._json(202, {"started": True, "source": source_id})

    def log_message(self, fmt: str, *args) -> None:
        # Don't spam the progress log with Health Check / browser polls.
        msg = fmt % args
        if any(x in msg for x in ("/v1/status", "/v1/check", "/v1/log", "/v1/sources", "GET / ", "GET /progress", "GET /status")):
            return
        append_log("http " + msg)


def main() -> None:
    env = load_env()
    bind = env.get("UPDATE_AGENT_BIND", "0.0.0.0")
    port = int(env.get("UPDATE_AGENT_PORT", "8410"))
    if not env.get("UPDATE_AGENT_TOKEN"):
        append_log("WARNING: UPDATE_AGENT_TOKEN is empty — all requests will be rejected")
    server = ThreadingHTTPServer((bind, port), Handler)
    append_log(f"listening on {bind}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
