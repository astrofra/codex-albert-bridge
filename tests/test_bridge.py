import contextlib
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import Mock, patch

import yaml

from codex_albert_bridge import cli
from codex_albert_bridge.config import DEFAULTS, model_catalog, render_profile, validate, write_configuration
from codex_albert_bridge.runtime import Gateway
from codex_albert_bridge.security import credential_path, load_credentials, private_directory, save_credentials


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="albert bridge test ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "state"
        private_directory(self.root)
        self.settings = {**DEFAULTS, "codex_home": str(Path(self.temp.name) / "codex home"), "codex": sys.executable}
        save_credentials(self.root, {"albert_key": "test-only-api-key", "gateway_key": "test-only-gateway-key"})

    def configured(self):
        write_configuration(self.root, self.settings)
        return Gateway(self.root)

    def test_generated_files_agree_on_model_and_token_budget(self):
        self.settings.update(model="other-model", context_window=100000, max_completion_tokens=20000, headroom_tokens=10000)
        profile = write_configuration(self.root, self.settings)
        parsed = tomllib.loads(profile.read_text())
        self.assertEqual(parsed["model_auto_compact_token_limit"], 70000)
        self.assertFalse(parsed["apps"]["_default"]["enabled"])
        self.assertEqual(parsed["model"], "other-model")
        proxy = yaml.safe_load((self.root / "proxy.yaml").read_text())
        entry = proxy["model_list"][0]
        self.assertEqual(entry["litellm_params"]["max_completion_tokens"], 20000)
        self.assertIn("max_tokens", entry["litellm_params"]["additional_drop_params"])
        self.assertEqual(entry["model_info"]["max_output_tokens"], 20000)
        model = json.loads((self.root / "models.json").read_text())["models"][0]
        self.assertEqual(model["slug"], "other-model")
        self.assertEqual(model["context_window"], 100000)
        self.assertFalse(model["supports_search_tool"])

    def test_windows_paths_round_trip_through_toml(self):
        root = Path('C:\\Users\\Example User\\bridge')
        profile = tomllib.loads(render_profile(root, self.settings))
        auth = profile["model_providers"]["albert_bridge"]["auth"]
        self.assertEqual(auth["args"][-2], str(root))
        self.assertEqual(auth["args"][-1], "--token")

    def test_existing_unmanaged_profile_is_not_overwritten(self):
        home = Path(self.settings["codex_home"])
        home.mkdir()
        profile = home / "albert-bridge.config.toml"
        profile.write_text('model = "my-model"\n')
        with self.assertRaisesRegex(ValueError, "already exists"):
            write_configuration(self.root, self.settings)
        self.assertEqual(profile.read_text(), 'model = "my-model"\n')
        self.assertFalse((self.root / "settings.json").exists())

    def test_managed_profile_from_another_installation_is_not_overwritten(self):
        profile = write_configuration(self.root, self.settings)
        previous = profile.read_bytes()
        other_root = self.root / "second"
        private_directory(other_root)
        with self.assertRaisesRegex(ValueError, "another bridge"):
            write_configuration(other_root, self.settings)
        self.assertEqual(profile.read_bytes(), previous)

    def test_can_change_port_when_an_unrelated_service_occupies_old_port(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            self.settings["port"] = listener.getsockname()[1]
            self.configured()
            new_port = 8420 if self.settings["port"] != 8420 else 8421
            with patch("codex_albert_bridge.cli.check_codex", return_value="0.162.1"):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(cli.configure(self.root, ["--port", str(new_port), "--no-key"]), 0)
            self.assertEqual(Gateway(self.root).settings["port"], new_port)

    def test_secrets_are_separate_from_generated_configuration(self):
        self.configured()
        for filename in ["settings.json", "models.json", "proxy.yaml"]:
            content = (self.root / filename).read_text()
            self.assertNotIn("test-only-api-key", content)
            self.assertNotIn("test-only-gateway-key", content)
        self.assertEqual(load_credentials(self.root)["albert_key"], "test-only-api-key")
        if os.name == "nt":
            self.assertNotIn(b"test-only-api-key", credential_path(self.root).read_bytes())
        else:
            self.assertEqual(credential_path(self.root).stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)

    def test_invalid_budgets_and_unsafe_endpoints_rejected(self):
        for update in [dict(context_window=1000), dict(max_completion_tokens=0),
                       dict(headroom_tokens=-1), dict(port=80), dict(profile="../other"),
                       dict(api_base="http://example.com/v1"), dict(api_base="https://key@example.com/v1"),
                       dict(api_base="https://example.com/v1?key=secret")]:
            with self.subTest(update=update), self.assertRaises(ValueError):
                validate({**self.settings, **update})

    def test_reused_pid_never_stops_an_unrelated_process(self):
        gateway = self.configured()
        gateway.pid_file.write_text(json.dumps({"pid": os.getpid(), "create_time": 1.0}))
        self.assertIsNone(gateway.owned_process())
        with self.assertRaisesRegex(RuntimeError, "stale"):
            gateway.stop()

    def test_busy_port_is_not_replaced(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            self.settings["port"] = listener.getsockname()[1]
            gateway = self.configured()
            with patch.object(gateway, "ready", return_value=False), patch("subprocess.Popen") as spawn:
                with self.assertRaisesRegex(RuntimeError, "occupied"):
                    gateway.start()
                spawn.assert_not_called()

    def test_launcher_forwards_arguments_without_a_shell_or_api_key(self):
        gateway = self.configured()
        prompt = 'Write a file called "two words.txt"; do not run $(anything) & echo no'
        with patch.object(gateway, "start", return_value="unused"), patch("subprocess.call", return_value=7) as call:
            with patch.dict(os.environ, {"ALBERT_API_KEY": "test-only-api-key", "ALBERT_GATEWAY_KEY": "test-only-gateway-key"}):
                self.assertEqual(gateway.launch(["exec", prompt]), 7)
            args, kw = call.call_args
            self.assertEqual(args[0][-2:], ["exec", prompt])
            self.assertNotIn("shell", kw)
            self.assertNotIn("ALBERT_API_KEY", kw["env"])
            self.assertNotIn("ALBERT_GATEWAY_KEY", kw["env"])

    def test_configure_no_key_and_version_guard(self):
        with patch("codex_albert_bridge.cli.check_codex", return_value="0.162.1"), patch.dict(os.environ, {"ALBERT_API_KEY": ""}):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.configure(self.root, ["--codex", sys.executable, "--codex-home", self.settings["codex_home"], "--no-key"]), 0)
        with patch("subprocess.run", return_value=Mock(stdout="codex-cli 0.100.0")):
            with self.assertRaisesRegex(ValueError, "0.134.0"):
                cli.check_codex("codex")

    def test_model_prompt_is_small_and_generic(self):
        catalog = model_catalog(self.settings)
        self.assertEqual(len(catalog["models"]), 1)
        self.assertLess(len(json.dumps(catalog)), 6000)

    def test_stop_before_configure_is_safe(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["--state-dir", str(self.root / "unconfigured"), "stop"]), 0)


    def test_start_status_stop_without_calling_albert(self):
        # Starts the real LiteLLM server, but only requests its local model list.
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.settings["port"] = probe.getsockname()[1]
        gateway = self.configured()
        try:
            key = gateway.start()
            self.assertTrue(gateway.ready(key))
            self.assertFalse(gateway.ready("wrong-test-key"))
            self.assertIsNotNone(gateway.owned_process())
            self.assertEqual(gateway.start(), key)
        finally:
            if gateway.owned_process():
                gateway.stop()
        self.assertFalse(gateway.port_busy())
        self.assertFalse(gateway.pid_file.exists())


if __name__ == "__main__":
    unittest.main()
