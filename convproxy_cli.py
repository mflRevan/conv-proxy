#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_PORT = 37374
DEFAULT_HOST = "0.0.0.0"
PID_FILE = ROOT / ".convproxy.pid"
LOG_FILE = ROOT / "convproxy.log"
CFG_DIR = Path.home() / ".config" / "conv-proxy"
CFG_FILE = CFG_DIR / "config.json"


def load_cfg() -> dict[str, Any]:
    if CFG_FILE.exists():
        try:
            return json.loads(CFG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "host": DEFAULT_HOST,
        "port": DEFAULT_PORT,
        "bridge_session_id": "",
        "dispatch_enabled": False,
        "openrouter_api_key": "",
        "gateway": {
            "url": "",
            "token": "",
            "password": "",
            "tailscale": False,
        },
    }


def save_cfg(cfg: dict[str, Any]):
    CFG_DIR.mkdir(parents=True, exist_ok=True)
    CFG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def run(cmd: list[str], check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


def sh(cmd: str, env: dict[str, str] | None = None, detached: bool = False):
    if detached:
        with open(LOG_FILE, "ab") as lf:
            p = subprocess.Popen(["bash", "-lc", cmd], stdout=lf, stderr=lf, start_new_session=True, env=env)
        return p
    return subprocess.run(["bash", "-lc", cmd], text=True, capture_output=True, env=env)


def is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def stop_existing():
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            if is_running(pid):
                os.kill(pid, 15)
                time.sleep(0.6)
            PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass
    # hard cleanup
    subprocess.run(["bash", "-lc", "pkill -f 'uvicorn webapp.app:app' || true"], capture_output=True)


def start_service(host: str, port: int, daemon: bool = True):
    stop_existing()
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    cmd = f"cd {ROOT} && source .venv-kokoro/bin/activate && export $(grep -v '^#' .env | xargs) && PYTHONPATH=. uvicorn webapp.app:app --host {host} --port {port}"
    p = sh(cmd, env=env, detached=daemon)
    if daemon:
        PID_FILE.write_text(str(p.pid), encoding="utf-8")
        for _ in range(30):
            r = subprocess.run(["bash", "-lc", f"curl -fsS --max-time 2 http://localhost:{port}/api/status"], capture_output=True)
            if r.returncode == 0:
                print(r.stdout.decode() if isinstance(r.stdout, bytes) else r.stdout)
                print(f"conv-proxy started (pid={p.pid})")
                return
            time.sleep(1)
        print("conv-proxy failed to start; tailing log:")
        print(LOG_FILE.read_text(encoding="utf-8", errors="ignore")[-2000:])
        sys.exit(1)
    else:
        os.execv("/bin/bash", ["bash", "-lc", cmd])


def status(port: int):
    r = subprocess.run(["bash", "-lc", f"curl -fsS --max-time 2 http://localhost:{port}/api/status"], capture_output=True, text=True)
    if r.returncode != 0:
        print("down")
        return
    print(r.stdout.strip())
    if PID_FILE.exists():
        print(f"pid_file={PID_FILE.read_text().strip()}")


def monitor(port: int):
    print("monitoring (ctrl+c to exit monitor)")
    while True:
        r = subprocess.run(["bash", "-lc", f"curl -fsS --max-time 2 http://localhost:{port}/api/status >/dev/null"], capture_output=True)
        print(f"[{time.strftime('%H:%M:%S')}] {'up' if r.returncode == 0 else 'down'}")
        time.sleep(3)


def openclaw_sessions():
    r = run(["openclaw", "sessions", "--json"])
    if r.returncode != 0:
        print(r.stderr)
        sys.exit(1)
    print(r.stdout)


def openclaw_agents():
    r = run(["openclaw", "agents", "list", "--json"])
    if r.returncode != 0:
        print(r.stderr)
        sys.exit(1)
    print(r.stdout)


def bind_session(session_id: str, dispatch_enabled: bool, port: int):
    payload = json.dumps({"session_id": session_id, "dispatch_enabled": dispatch_enabled})
    r = subprocess.run(["bash", "-lc", f"curl -fsS -X POST http://localhost:{port}/api/bridge/bind -H 'Content-Type: application/json' -d '{payload}'"], text=True, capture_output=True)
    print(r.stdout or r.stderr)


def bind_main(port: int):
    r = subprocess.run(["bash", "-lc", f"curl -fsS -X POST http://localhost:{port}/api/bridge/bind-main"], text=True, capture_output=True)
    print(r.stdout or r.stderr)


def toggle_dispatch(enabled: bool, port: int):
    payload = json.dumps({"enabled": enabled})
    r = subprocess.run(["bash", "-lc", f"curl -fsS -X POST http://localhost:{port}/api/bridge/dispatch -H 'Content-Type: application/json' -d '{payload}'"], text=True, capture_output=True)
    print(r.stdout or r.stderr)


def bridge_status(port: int):
    r = subprocess.run(["bash", "-lc", f"curl -fsS http://localhost:{port}/api/bridge/status"], text=True, capture_output=True)
    print(r.stdout or r.stderr)


def onboard():
    cfg = load_cfg()
    print("=== conv-proxy onboarding ===")
    v = input(f"Host [{cfg.get('host', DEFAULT_HOST)}]: ").strip() or cfg.get("host", DEFAULT_HOST)
    p = input(f"Port [{cfg.get('port', DEFAULT_PORT)}]: ").strip() or str(cfg.get("port", DEFAULT_PORT))
    key = input("OpenRouter API key (leave empty to keep current): ").strip()
    gurl = input("Gateway URL (optional, ws://...): ").strip() or cfg.get("gateway", {}).get("url", "")
    gtok = input("Gateway token (optional): ").strip() or cfg.get("gateway", {}).get("token", "")
    gpwd = input("Gateway password (optional): ").strip() or cfg.get("gateway", {}).get("password", "")

    cfg["host"] = v
    cfg["port"] = int(p)
    if key:
        cfg["openrouter_api_key"] = key
        envp = ROOT / ".env"
        cur = envp.read_text(encoding="utf-8") if envp.exists() else ""
        if "OPENROUTER_API_KEY=" in cur:
            lines = []
            for ln in cur.splitlines():
                if ln.startswith("OPENROUTER_API_KEY="):
                    lines.append(f"OPENROUTER_API_KEY={key}")
                else:
                    lines.append(ln)
            envp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        else:
            envp.write_text(cur + ("\n" if cur and not cur.endswith("\n") else "") + f"OPENROUTER_API_KEY={key}\n", encoding="utf-8")
    cfg["gateway"] = {"url": gurl, "token": gtok, "password": gpwd, "tailscale": "ts.net" in gurl}
    save_cfg(cfg)
    print(f"saved {CFG_FILE}")


def new_session(agent: str, message: str):
    msg = f"/new {message}" if not message.startswith("/new") else message
    r = run(["openclaw", "agent", "--agent", agent, "--message", msg, "--json"])
    print(r.stdout or r.stderr)


def main():
    parser = argparse.ArgumentParser(description="conv-proxy production CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("onboard")

    pstart = sub.add_parser("start")
    pstart.add_argument("--host", default=None)
    pstart.add_argument("--port", type=int, default=None)
    pstart.add_argument("--foreground", action="store_true")

    pstop = sub.add_parser("stop")
    pstatus = sub.add_parser("status")
    pstatus.add_argument("--port", type=int, default=None)

    pmon = sub.add_parser("monitor")
    pmon.add_argument("--port", type=int, default=None)

    sub.add_parser("sessions")
    sub.add_parser("agents")

    pbind = sub.add_parser("bind")
    pbind.add_argument("session_id")
    pbind.add_argument("--dispatch", action="store_true")
    pbind.add_argument("--port", type=int, default=None)

    pbm = sub.add_parser("bind-main")
    pbm.add_argument("--port", type=int, default=None)

    pdisp = sub.add_parser("dispatch")
    pdisp.add_argument("state", choices=["on", "off"])
    pdisp.add_argument("--port", type=int, default=None)

    pbs = sub.add_parser("bridge-status")
    pbs.add_argument("--port", type=int, default=None)

    pnew = sub.add_parser("new-session")
    pnew.add_argument("--agent", default="main")
    pnew.add_argument("--message", default="hello")

    args = parser.parse_args()
    cfg = load_cfg()
    port = args.port if hasattr(args, "port") and args.port else int(cfg.get("port", DEFAULT_PORT))

    if args.cmd == "onboard":
        onboard()
    elif args.cmd == "start":
        host = args.host or cfg.get("host", DEFAULT_HOST)
        start_service(host, args.port or int(cfg.get("port", DEFAULT_PORT)), daemon=not args.foreground)
    elif args.cmd == "stop":
        stop_existing()
        print("stopped")
    elif args.cmd == "status":
        status(port)
    elif args.cmd == "monitor":
        monitor(port)
    elif args.cmd == "sessions":
        openclaw_sessions()
    elif args.cmd == "agents":
        openclaw_agents()
    elif args.cmd == "bind":
        bind_session(args.session_id, args.dispatch, port)
    elif args.cmd == "bind-main":
        bind_main(port)
    elif args.cmd == "dispatch":
        toggle_dispatch(args.state == "on", port)
    elif args.cmd == "bridge-status":
        bridge_status(port)
    elif args.cmd == "new-session":
        new_session(args.agent, args.message)


if __name__ == "__main__":
    main()
