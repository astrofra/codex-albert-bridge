"""Cross-platform, loopback-only gateway lifecycle management."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

from filelock import FileLock
import psutil

from .security import atomic_write, load_credentials

CLIENT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class Gateway:
    def __init__(self, root: Path):
        self.root = root
        try:
            self.settings = json.loads((root / "settings.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise RuntimeError("Run 'codex-albert configure' first.") from None
        self.url = f'http://127.0.0.1:{self.settings["port"]}'
        self.pid_file = root / "proxy.pid.json"
        self.lock = FileLock(root / "startup.lock", timeout=50)
        self._child = None

    def credentials(self) -> dict:
        values = load_credentials(self.root)
        values["albert_key"] = os.environ.get("ALBERT_API_KEY") or values.get("albert_key", "")
        if not values["albert_key"]:
            raise RuntimeError("No Albert API key is configured. Run 'codex-albert configure'.")
        return values

    def ready(self, key: str) -> bool:
        req = urllib.request.Request(self.url + "/v1/models", headers={"Authorization": "Bearer " + key})
        try:
            with CLIENT.open(req, timeout=1) as response:
                data = json.load(response)
            return any(m.get("id") == self.settings["model"] for m in data.get("data", []))
        except (OSError, ValueError, urllib.error.URLError):
            return False

    def port_busy(self) -> bool:
        with socket.socket() as probe:
            probe.settimeout(1)
            return probe.connect_ex(("127.0.0.1", self.settings["port"])) == 0

    def owned_process(self):
        if not self.pid_file.exists():
            return None
        try:
            record = json.loads(self.pid_file.read_text(encoding="utf-8"))
            process = psutil.Process(record["pid"])
            if abs(process.create_time() - record["create_time"]) > 0.01:
                return None  # PID has been reused.
            if str(self.root / "proxy.yaml") not in process.cmdline():
                return None
            return process
        except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError, KeyError):
            return None

    def start(self) -> str:
        values = self.credentials()
        key = values["gateway_key"]
        with self.lock:
            if self.ready(key):
                return key
            if self.port_busy():
                raise RuntimeError("The configured port is occupied by another service. Choose a different --port with configure.")
            if self.owned_process():
                raise RuntimeError("The gateway process is still starting or unhealthy. Run 'codex-albert stop' before retrying.")
            env = os.environ.copy()
            env.update({"ALBERT_API_KEY": values["albert_key"], "ALBERT_GATEWAY_KEY": key,
                        "LITELLM_TELEMETRY": "False", "LITELLM_LOG": "ERROR",
                        "DO_NOT_TRACK": "1", "DEBUG": "false", "LITELLM_MODE": "PRODUCTION"})
            options = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS}
                       if os.name == "nt" else {"start_new_session": True})
            fd = os.open(self.root / "proxy.log", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "ab", buffering=0) as output:
                child = subprocess.Popen(
                    [sys.executable, "-m", "litellm.proxy.proxy_cli", "--config", str(self.root / "proxy.yaml"),
                     "--host", "127.0.0.1", "--port", str(self.settings["port"]), "--num_workers", "1"],
                    cwd=self.root, env=env, stdin=subprocess.DEVNULL,
                    stdout=output, stderr=output, **options,
                )
            self._child = child
            try:
                record = {"pid": child.pid, "create_time": psutil.Process(child.pid).create_time()}
                atomic_write(self.pid_file, json.dumps(record).encode())
                deadline = time.monotonic() + 40
                while time.monotonic() < deadline:
                    if child.poll() is not None:
                        raise RuntimeError("The gateway exited during startup. Inspect its private proxy.log.")
                    if self.ready(key):
                        return key
                    time.sleep(0.25)
                raise RuntimeError("Gateway startup timed out. Inspect its private proxy.log.")
            except BaseException:
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.kill()
                self.pid_file.unlink(missing_ok=True)
                raise

    def stop(self) -> None:
        with self.lock:
            process = self.owned_process()
            if process:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except psutil.TimeoutExpired:
                    raise RuntimeError("The gateway has not stopped yet; retry in a few seconds.") from None
                if self._child is not None:
                    self._child.poll()
            elif self.pid_file.exists():
                raise RuntimeError("The PID record is stale or unverifiable; no process was stopped. Check it before removing the record.")
            self.pid_file.unlink(missing_ok=True)

    def launch(self, arguments: list[str]) -> int:
        self.start()
        env = os.environ.copy()
        env["CODEX_HOME"] = self.settings["codex_home"]
        # Only the gateway child needs the upstream API key.
        env.pop("ALBERT_API_KEY", None)
        env.pop("ALBERT_GATEWAY_KEY", None)
        cmd = [self.settings["codex"], "--no-daemon", "--profile", self.settings["profile"], *arguments]
        return subprocess.call(cmd, env=env)
