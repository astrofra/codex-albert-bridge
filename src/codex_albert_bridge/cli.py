"""Command-line entry point. Secrets are never accepted as command arguments."""

import argparse
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import urllib.request

from . import __version__
from .config import DEFAULTS, codex_home, resolve_codex, state_home, validate, write_configuration
from .runtime import Gateway
from .security import credential_path, load_credentials, private_directory, save_credentials

HELP = """Codex Albert Bridge

  codex-albert configure [options]  Create private configuration and enter an API key
  codex-albert start                Start the local gateway
  codex-albert status               Check the local gateway (no model call)
  codex-albert stop                 Stop this installation's gateway
  codex-albert doctor [--check-api]  Check configuration, CLI, and optionally Albert access
  codex-albert [run] [CODEX ARGS]    Start the gateway and launch Codex

Use 'configure --help' for settings. All other arguments, including exec,
resume, -C and their arguments, are passed to Codex. Global --state-dir PATH
must precede the command. No background service is installed at login.
"""


def check_codex(binary: str) -> str:
    result = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=15, check=True)
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", result.stdout)
    if not match or tuple(map(int, match.groups())) < (0, 134, 0):
        raise ValueError("Codex 0.134.0 or newer is required for separate profile files. Tested release: 0.162.1.")
    return match.group(0)


def configure(root: Path, arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="codex-albert configure")
    parser.add_argument("--model")
    parser.add_argument("--api-base", help="HTTPS Albert-compatible API base; your key is sent to this host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--context-window", type=int)
    parser.add_argument("--max-completion-tokens", type=int)
    parser.add_argument("--headroom-tokens", type=int)
    parser.add_argument("--profile")
    parser.add_argument("--codex", help="Path to a native Codex CLI executable")
    parser.add_argument("--codex-home", type=Path)
    parser.add_argument("--no-key", action="store_true", help="Prepare configuration without prompting for an API key")
    args = parser.parse_args(arguments)
    settings = dict(DEFAULTS)
    if (root / "settings.json").exists():
        old = Gateway(root)
        if old.owned_process():
            raise RuntimeError("Stop the gateway before changing its configuration.")
        settings.update(old.settings)
    for name in DEFAULTS:
        value = getattr(args, name, None)
        if value is not None:
            settings[name] = value
    settings["codex"] = resolve_codex(args.codex or settings.get("codex"))
    settings["codex_home"] = str((args.codex_home or Path(settings.get("codex_home", codex_home()))).expanduser().resolve())
    validate(settings)
    version = check_codex(settings["codex"])
    values = load_credentials(root) if credential_path(root).exists() else {"albert_key": "", "gateway_key": "sk-" + secrets.token_urlsafe(40)}
    key = os.environ.get("ALBERT_API_KEY")
    if not key and not args.no_key:
        if not sys.stdin.isatty():
            raise ValueError("Use an interactive terminal to enter the key, or supply ALBERT_API_KEY through your environment.")
        prompt = "Albert API key (hidden; Enter keeps the existing key): " if values["albert_key"] else "Albert API key (hidden): "
        key = getpass.getpass(prompt)
    if key:
        if any(c.isspace() for c in key) or not key.isascii():
            raise ValueError("The API key must be ASCII with no whitespace.")
        values["albert_key"] = key
    if not values["albert_key"] and not args.no_key:
        raise ValueError("An Albert API key is required.")
    private_directory(root)
    profile = write_configuration(root, settings)
    save_credentials(root, values)
    print(f"Configuration ready for Codex {version}. Profile: {profile}")
    print(f"Private bridge files: {root}")
    print("Run 'codex-albert doctor --check-api' to verify model access, then 'codex-albert'.")
    return 0


def doctor(gateway: Gateway, check_api: bool) -> int:
    validate(gateway.settings)
    print(f"Bridge {__version__}; Codex {check_codex(gateway.settings['codex'])}")
    print(f"Model: {gateway.settings['model']}")
    print(f"Gateway: {gateway.url} (loopback only)")
    if check_api:
        values = gateway.credentials()
        # No prompt, completion, or local project data is transmitted by this check.
        request = urllib.request.Request(gateway.settings["api_base"].rstrip("/") + "/models",
                                         headers={"Authorization": "Bearer " + values["albert_key"]})
        with urllib.request.urlopen(request, timeout=30) as response:
            models = json.load(response).get("data", [])
        if not any(m.get("id") == gateway.settings["model"] for m in models):
            raise ValueError("The configured model is absent from your Albert model catalog.")
        print("Albert authentication and model availability: OK (no completion requested).")
    return 0


def main(argv: list[str] | None = None) -> int:
    os.umask(0o077)
    args = list(sys.argv[1:] if argv is None else argv)
    root = state_home()
    if args[:1] == ["--state-dir"]:
        if len(args) < 2:
            print("Missing --state-dir path.", file=sys.stderr)
            return 2
        root = Path(args[1]).expanduser().resolve()
        args = args[2:]
    command = args[0] if args else "run"
    aliases = {"--start-proxy": "start", "--stop-proxy": "stop", "--status": "status"}
    command = aliases.get(command, command)
    try:
        if command in {"-h", "--help"}:
            print(HELP)
            return 0
        if command == "--version":
            print(__version__)
            return 0
        if command == "configure":
            return configure(root, args[1:])
        if command == "stop" and not (root / "settings.json").exists():
            print("No gateway has been configured.")
            return 0
        gateway = Gateway(root)
        if command == "doctor":
            if args[1:] not in ([], ["--check-api"]):
                raise ValueError("Usage: codex-albert doctor [--check-api]")
            return doctor(gateway, "--check-api" in args)
        if command in {"start", "stop", "status", "--token"}:
            if len(args) != 1:
                raise ValueError(f"{command} does not accept extra arguments.")
            if command == "stop":
                gateway.stop()
                print("Gateway stopped.")
            elif command == "status":
                running = gateway.ready(load_credentials(root)["gateway_key"])
                print("Gateway running." if running else "Gateway stopped or unavailable.")
                return 0 if running else 1
            else:
                key = gateway.start()
                print(key if command == "--token" else f"Gateway ready at {gateway.url}")
            return 0
        return gateway.launch(args[1:] if command == "run" else args)
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        # Do not print HTTP response bodies or request headers; these can contain secrets.
        print(f"Albert bridge: {error}", file=sys.stderr)
        return 1
