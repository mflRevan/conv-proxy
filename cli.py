#!/usr/bin/env python3
"""
clawproxy — OpenClaw Observer & Planner Client

CLI entry point. Install with:
    pip install -e .
Then use:
    clawproxy launch
    clawproxy status
    clawproxy uninstall
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

__version__ = "0.1.0"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def get_data_dir() -> Path:
    """~/.clawproxy — persistent config/data directory."""
    return Path.home() / ".clawproxy"


def get_project_root() -> Path:
    """The clawproxy source root (where this file lives)."""
    return Path(__file__).resolve().parent


def load_config() -> dict:
    config_file = get_data_dir() / "config.json"
    if config_file.exists():
        try:
            with open(config_file) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_config(config: dict) -> None:
    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    config_file = data_dir / "config.json"
    with open(config_file, "w") as f:
        json.dump(config, f, indent=2)


# ---------------------------------------------------------------------------
# Gateway discovery
# ---------------------------------------------------------------------------

def discover_gateway() -> dict:
    """Try to discover the local OpenClaw gateway."""
    candidates = [
        Path.home() / ".openclaw" / "openclaw.json",
        Path.home() / ".openclaw-dev" / "openclaw.json",
    ]
    for cfg_path in candidates:
        if cfg_path.exists():
            try:
                with open(cfg_path) as f:
                    cfg = json.load(f)
                gw = cfg.get("gateway", {})
                port = gw.get("port", 18789)
                token = gw.get("auth", {}).get("token", "")
                if not token:
                    token = gw.get("auth", {}).get("sharedToken", "")
                return {
                    "url": f"ws://127.0.0.1:{port}",
                    "origin": f"http://127.0.0.1:{port}",
                    "token": token,
                    "port": port,
                    "config_path": str(cfg_path),
                }
            except Exception:
                continue
    return {}


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_launch(args):
    """Launch the clawproxy server."""
    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    # Gateway discovery
    gw = discover_gateway()
    if gw:
        print(f"  📡 Gateway discovered at {gw['url']} (from {gw['config_path']})")
        os.environ.setdefault("GATEWAY_URL", gw["url"])
        os.environ.setdefault("GATEWAY_ORIGIN", gw["origin"])
        if gw["token"]:
            os.environ.setdefault("GATEWAY_TOKEN", gw["token"])
    else:
        print("  ⚠️  No OpenClaw gateway found. Set GATEWAY_TOKEN and GATEWAY_URL manually.")

    # Override from CLI flags
    if args.port:
        os.environ["PORT"] = str(args.port)
    if args.host:
        os.environ["HOST"] = args.host
    if args.gateway_url:
        os.environ["GATEWAY_URL"] = args.gateway_url
    if args.gateway_token:
        os.environ["GATEWAY_TOKEN"] = args.gateway_token

    config = load_config()

    openrouter_key = os.environ.get("OPENROUTER_API_KEY") or config.get("openrouter", {}).get("apiKey", "")
    hf_token = os.environ.get("HUGGINGFACE_HUB_TOKEN") or os.environ.get("HF_TOKEN") or config.get("hf", {}).get("token", "")
    if hf_token:
        os.environ.setdefault("HUGGINGFACE_HUB_TOKEN", hf_token)
        os.environ.setdefault("HF_TOKEN", hf_token)
    if not openrouter_key:
        if sys.stdin.isatty():
            openrouter_key = input("Enter your OpenRouter API key: ").strip()
            if openrouter_key:
                config.setdefault("openrouter", {})["apiKey"] = openrouter_key
                save_config(config)
        else:
            print("  ❌ OPENROUTER_API_KEY not set. Run with a TTY or set it in ~/.clawproxy/config.json")
            sys.exit(1)
    if openrouter_key:
        os.environ.setdefault("OPENROUTER_API_KEY", openrouter_key)

    gateway_token = os.environ.get("GATEWAY_TOKEN") or config.get("gateway", {}).get("token", "")
    if not gateway_token:
        if sys.stdin.isatty():
            gateway_token = input("Enter your Gateway token: ").strip()
            if gateway_token:
                config.setdefault("gateway", {})["token"] = gateway_token
                save_config(config)
        else:
            print("  ❌ GATEWAY_TOKEN not set. Run with a TTY or set it in ~/.clawproxy/config.json")
            sys.exit(1)
    if gateway_token:
        os.environ.setdefault("GATEWAY_TOKEN", gateway_token)

    host = os.environ.get("HOST", "0.0.0.0")
    port = os.environ.get("PORT", "37374")

    print(f"\n  🦀 clawproxy v{__version__}")
    print(f"  → Server:  http://{host}:{port}")
    print(f"  → Gateway: {os.environ.get('GATEWAY_URL', 'not set')}")
    print()

    import uvicorn
    uvicorn.run(
        "src.server.app:app",
        host=host,
        port=int(port),
        log_level="info" if not args.verbose else "debug",
        reload=args.reload,
    )


def cmd_status(args):
    """Check clawproxy and gateway status."""
    import urllib.request

    port = args.port or 37374
    url = f"http://127.0.0.1:{port}/api/status"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            data = json.loads(resp.read())
            gw = data.get("gateway", {})
            voice = data.get("voice", {})
            print(f"  clawproxy:  running on :{port}")
            print(f"  gateway:    {gw.get('state', '?')} (connected={gw.get('connected', False)})")
            print(f"  voice:      pipeline={voice.get('pipeline', False)} stt={voice.get('stt', False)} tts={voice.get('tts', False)}")
    except Exception as e:
        print(f"  clawproxy not reachable on :{port} ({e})")

    # Check gateway directly
    gw = discover_gateway()
    if gw:
        try:
            health_url = f"http://127.0.0.1:{gw['port']}/health"
            with urllib.request.urlopen(health_url, timeout=3) as resp:
                print(f"  openclaw:   gateway healthy on :{gw['port']}")
        except Exception:
            print(f"  openclaw:   gateway not reachable on :{gw['port']}")


def cmd_setup(args):
    """Initialize clawproxy data directory and config."""
    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    config_file = data_dir / "config.json"
    if config_file.exists() and not args.force:
        print(f"  Config already exists at {config_file}")
        print("  Use --force to overwrite.")
        return

    # Discover gateway
    gw = discover_gateway()

    print("\n  🔧 Configure clawproxy")
    openrouter_key = input("Enter your OpenRouter API key: ").strip()
    hf_token = input("Enter your Hugging Face token (optional): ").strip()

    gateway_default = gw.get("token", "") if gw else ""
    gateway_prompt = "Enter your Gateway token"
    if gateway_default:
        gateway_prompt += f" [{gateway_default}]"
    gateway_prompt += ": "
    gateway_token = input(gateway_prompt).strip() or gateway_default

    config = {
        "openrouter": {
            "apiKey": openrouter_key,
        },
        "hf": {
            "token": hf_token,
        },
        "gateway": {
            "url": gw.get("url", "ws://127.0.0.1:18789"),
            "token": gateway_token,
        },
        "server": {
            "host": "0.0.0.0",
            "port": 37374,
        },
        "voice": {
            "enabled": True,
            "wakewordEnabled": True,
            "wakewordThreshold": 0.55,
            "wakewordActiveWindowMs": 10000,
        },
    }

    save_config(config)

    print(f"  ✅ Config written to {config_file}")
    if gw:
        print(f"  📡 Gateway auto-discovered: {gw['url']}")
    else:
        print("  ⚠️  No gateway found. Edit config.json to set gateway.url and gateway.token.")


def cmd_uninstall(args):
    """Remove clawproxy data directory and optionally the venv."""
    data_dir = get_data_dir()

    if not args.yes:
        answer = input(f"  Remove {data_dir}? [y/N] ").strip().lower()
        if answer != "y":
            print("  Cancelled.")
            return

    if data_dir.exists():
        shutil.rmtree(data_dir)
        print(f"  ✅ Removed {data_dir}")
    else:
        print(f"  Nothing to remove at {data_dir}")

    if args.purge:
        venv = get_project_root() / ".venv-kokoro"
        if venv.exists():
            shutil.rmtree(venv)
            print(f"  ✅ Removed venv at {venv}")


def cmd_version(args):
    print(f"clawproxy v{__version__}")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clawproxy",
        description="🦀 ClawProxy — OpenClaw Observer & Planner Client",
    )
    parser.add_argument("-V", "--version", action="store_true", help="Show version")
    sub = parser.add_subparsers(dest="command")

    # launch
    p_launch = sub.add_parser("launch", help="Start the clawproxy server")
    p_launch.add_argument("--port", type=int, default=None, help="Server port (default: 37374)")
    p_launch.add_argument("--host", default=None, help="Bind host (default: 0.0.0.0)")
    p_launch.add_argument("--gateway-url", default=None, help="Override gateway WS URL")
    p_launch.add_argument("--gateway-token", default=None, help="Override gateway auth token")
    p_launch.add_argument("--reload", action="store_true", help="Enable hot-reload (dev)")
    p_launch.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    p_launch.set_defaults(func=cmd_launch)

    # status
    p_status = sub.add_parser("status", help="Check proxy and gateway status")
    p_status.add_argument("--port", type=int, default=None, help="Proxy port to check")
    p_status.set_defaults(func=cmd_status)

    # setup
    p_setup = sub.add_parser("setup", help="Initialize config and data directory")
    p_setup.add_argument("--force", action="store_true", help="Overwrite existing config")
    p_setup.set_defaults(func=cmd_setup)

    # uninstall
    p_uninstall = sub.add_parser("uninstall", help="Remove clawproxy data and config")
    p_uninstall.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    p_uninstall.add_argument("--purge", action="store_true", help="Also remove venv")
    p_uninstall.set_defaults(func=cmd_uninstall)

    # version
    p_ver = sub.add_parser("version", help="Show version")
    p_ver.set_defaults(func=cmd_version)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.version:
        cmd_version(args)
        return

    if not args.command:
        parser.print_help()
        return

    # Ensure project root is in sys.path for imports
    root = get_project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    # Load .env
    try:
        from dotenv import load_dotenv
        load_dotenv(root / ".env")
    except ImportError:
        pass

    args.func(args)


if __name__ == "__main__":
    main()
