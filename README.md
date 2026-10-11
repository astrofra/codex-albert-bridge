# Codex Albert Bridge

Use the Codex CLI with a model hosted on [Albert](https://albert.api.etalab.gouv.fr/), through a local LiteLLM gateway.

```text
Codex CLI -> http://127.0.0.1:8417/v1 -> LiteLLM -> Albert Chat Completions API
             OpenAI Responses API
```

The default model is `deepseek-v4-flash-0731`. This is a portable version of a working local integration, with a small public model catalog and no copied API keys, user paths, conversations, or private configuration. It is an independent project, not an official OpenAI or DINUM product.

## Install on Windows

Use **native Windows PowerShell 5.1 or PowerShell 7**, not a WSL shell. Installation is per user and does not require administrator rights. You need:

- Python **3.12**, available through `py -3.12` or an explicit executable path;
- Node.js **20 or newer**, including npm;
- an Albert API key with access to the configured model;
- internet access to download packages and use Albert.

Install Python from [python.org](https://www.python.org/downloads/windows/) and Node.js LTS from [nodejs.org](https://nodejs.org/en/download). Python is also available through `winget install --exact --id Python.Python.3.12`. Open a fresh terminal after installing prerequisites.

Download or clone this repository, open PowerShell in its directory, and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

`Bypass` applies only to this process; the installer does not change your permanent execution policy. Review the script before running it. Organization policies may still prevent execution.

The installer creates an isolated Python environment and a private **Codex CLI 0.162.1** installation under `%LOCALAPPDATA%\Programs\CodexAlbertBridge`. It adds the bridge's launcher directory to your user PATH. Existing Codex installations and the default Codex configuration are not replaced.

Enter your Albert key at the hidden prompt. On Windows, both the Albert key and the generated local gateway key are encrypted with **DPAPI for your Windows account**, outside this repository. No key is passed on the command line.

Open a new terminal and verify the installation:

```powershell
codex-albert doctor --check-api
cd C:\path\to\your\project
codex-albert
```

`doctor --check-api` checks authentication and the model catalog. It does not ask the model to generate a response. Your first real Codex task does consume Albert quota.

Installer options:

```powershell
# Choose a Python installation, destination, or local port.
.\install.ps1 -PythonExecutable 'C:\Python312\python.exe' -InstallDir "$env:LOCALAPPDATA\MyBridge" -Port 8420

# Install without prompting for a key or modifying PATH (for automation).
.\install.ps1 -SkipConfigure -NoPath
```

`-SkipConfigure` still generates configuration; it only skips the API-key prompt. Run `configure` later. For unattended setup, inject `ALBERT_API_KEY` through your secret manager's environment, not a checked-in script. `-CodexVersion` selects another explicit npm version; other versions require compatibility testing.

## Install on macOS or Linux

Install Python 3.12 and a packaged [Codex CLI](https://learn.chatgpt.com/docs/cli) first. Codex **0.134.0 or newer** is required for separate profile files; this bridge was tested with **0.162.1**. From the repository:

```sh
python3.12 -m venv "$HOME/.local/share/codex-albert-bridge/venv"
"$HOME/.local/share/codex-albert-bridge/venv/bin/python" -m pip install .
"$HOME/.local/share/codex-albert-bridge/venv/bin/codex-albert" configure
```

Add `$HOME/.local/share/codex-albert-bridge/venv/bin` to your PATH, or use the full launcher path. macOS/Linux credentials are stored as a local plaintext JSON file with mode `600`, in a directory with mode `700`. They are not encrypted on these platforms.

## Everyday commands

| Command | Purpose |
| --- | --- |
| `codex-albert` | Start the gateway if needed, then open Codex with the Albert profile. |
| `codex-albert -C PATH` | Open a project through Albert. |
| `codex-albert exec "Explain this project"` | Run a noninteractive task. |
| `codex-albert resume --last` | Resume the last compatible Codex session. |
| `codex-albert start` | Start only the gateway. |
| `codex-albert status` | Check the local gateway, without contacting the model. |
| `codex-albert stop` | Stop this bridge's gateway. |
| `codex-albert configure` | Enter or replace the key and regenerate configuration. Stop the gateway first. |
| `codex-albert doctor --check-api` | Check configuration, CLI version, authentication, and model availability. |
| `codex-albert run --help` | Show Codex's own help. |

`--start-proxy`, `--stop-proxy`, and `--status` are also accepted for compatibility with the original bridge. `status` returns exit code 1 when the gateway is not running. `--token` is reserved for Codex's authentication helper: it prints the **local gateway key** and should not be run in shared terminals or logs.

To leave Albert, exit the Codex session, optionally run `codex-albert stop`, and use your usual `codex` command. The gateway remains running after you exit Codex, but is not installed as a login service.

## Configuration and limits

Generated files are stored in `$CODEX_HOME/albert-bridge`, or `~/.codex/albert-bridge` when `CODEX_HOME` is unset. The dedicated profile is `~/.codex/albert-bridge.config.toml`. You can use `ALBERT_BRIDGE_HOME` or a leading `--state-dir PATH` to select a different private state directory.

| Setting | Default |
| --- | ---: |
| Model | `deepseek-v4-flash-0731` |
| Context window (input + reserved output) | 131,072 tokens |
| Maximum completion | 32,768 tokens |
| Automatic compaction threshold | 81,920 tokens |
| Extra context headroom | 16,384 tokens |
| Listen address | `127.0.0.1:8417` |
| App connectors | Disabled in this profile |

App connector schemas previously consumed about 70,000 extra input tokens and caused repeated compactions. This profile disables connectors such as Drive, Pages and Sites while retaining local terminal and file tools. It inherits other user and project settings, including custom MCP servers; those can still add context. Do not re-enable all connectors without checking their token cost.

The maximum completion is a **reservation**, not a request to write that many tokens. LiteLLM drops competing `max_tokens` values and applies the configured `max_completion_tokens`. Compaction is orchestrated by Codex; the model on Albert writes the summary. Large individual tool outputs can still overflow the context despite the safety margin.

For details, model changes, update/uninstall procedures, and troubleshooting, see:

- [Configuration and architecture](docs/configuration.md)
- [Complete public configuration examples](examples/README.md)
- [Privacy and publication](docs/privacy.md)
- [Troubleshooting and maintenance](docs/troubleshooting.md)

## Development and validation

```sh
python3.12 -m venv .venv
# Windows: .venv\Scripts\python.exe
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests -v
```

The tests cover configuration consistency, secret storage, path quoting, occupied ports, PID reuse, argument forwarding, and a real local LiteLLM start/status/stop cycle. They use dummy credentials and do not request Albert completions. The GitHub Actions workflow includes Windows, macOS and Linux, plus a Windows installer smoke test without an API key. It runs only after you push; no CI result is implied by its presence.

Before publishing, inspect `git diff --cached` and follow [the privacy checks](docs/privacy.md). The existing MIT license and Git attribution are preserved.
