# Troubleshooting and maintenance

## Command not found

Open a fresh terminal after the Windows installer updates your user PATH. The default launcher can always be called directly:

```powershell
& "$env:LOCALAPPDATA\Programs\CodexAlbertBridge\venv\Scripts\codex-albert.exe" --help
```

With `-NoPath`, use that full path or update PATH yourself. On macOS/Linux, activate the installation's virtual environment or add its `bin` directory to PATH.

## Python or npm is missing

The installer checks prerequisites before writing the installation. It requires Python 3.12 and Node.js 20+ with npm. If Python is installed but not found, use `-PythonExecutable 'C:\path\to\python.exe'`. Microsoft Store Python aliases are not a substitute for a working interpreter.

The project pins LiteLLM and the installer pins Codex, but transitive dependencies are resolved for the host platform by pip/npm. A restricted package index, blocked downloads, or an unsupported architecture can still cause installation to fail. Windows x64 is the primary installer target; other architectures need separate validation.

## Incomplete Codex package or profile errors

The launcher adds `--no-daemon`. The Windows installer obtains a complete Codex package from npm rather than copying a VS Code extension binary. An externally installed CLI must support the configuration schema; Codex 0.134.0 introduced the separate profile-file format used here. The tested release is 0.162.1.

An existing unmanaged profile is never overwritten. Choose another name with `configure --profile NAME`. An existing personal `albert` profile is separate from the default `albert-bridge` profile.

## Gateway cannot start

Run `codex-albert status`, then inspect the private `proxy.log` in the bridge state directory. Do not publish the entire log without checking it for sensitive information.

The default port may already be used by an older bridge or another service. The launcher refuses to replace it. Stop this installation's gateway before reconfiguration. If the port belongs to another service, choose a different port; you do not need to stop that other service.

```sh
codex-albert stop
codex-albert configure --port 8420
codex-albert start
```

A stale PID record is not permission to kill a process. If `stop` reports one, verify that this installation's gateway is no longer running, then remove only its `proxy.pid.json` file and retry.

## Gateway runs but Albert returns an error

`status` verifies the local server and its model list, not successful upstream inference. Use `doctor --check-api` to check your key and model access. HTTP 401/403 can mean invalid credentials or missing access; a rate limit or provider outage can also stop generation.

For a generation and tool-use check, use a disposable project directory:

```sh
codex-albert exec "Create hello.txt containing HELLO, then read it back and verify the contents."
```

This uses Albert quota and may request normal Codex approvals. The bridge preserves Codex's approval and sandbox settings.

A clean Codex home may report an unauthorized OpenAI plugin-catalog request even while Albert inference works. Plugin discovery is separate from Albert authentication. Judge the model path using the actual completion and tool results.

## Context exceeded or repeated compactions

Input plus **reserved** output must fit the model window. The default 131,072-token context reserves 32,768 output tokens and 16,384 tokens of additional headroom. Codex compacts at 81,920 tokens of active context.

The profile disables app connectors to avoid adding their full schemas to every request. Re-enabling them, adding many custom MCP tools, or sending large tool results can consume the remaining space. Summaries cannot remove tool definitions that are resent on the next request.

Start a new session after changing configuration. If an old session is already too large, provide a concise handoff in a fresh one. Smaller tool outputs or a reduced completion reservation can help; do not blindly raise the compaction threshold or invent a larger model context. These budgets reduce risk, but do not guarantee that every single large input will fit.

## Update

1. Exit active Albert sessions and run `codex-albert stop`.
2. Update this source checkout.
3. On Windows, rerun `install.ps1` with the same installation directory and options. On macOS/Linux, rerun the installation environment's `python -m pip install --upgrade .`.
4. Run `codex-albert configure`, retaining or replacing the existing key, then `doctor --check-api`.
5. Open a new Codex session.

Reconfiguration preserves saved settings unless explicitly overridden, and does not rotate the local gateway key. Back up generated files before making custom edits you want to keep. The original personal installation is not a dependency of this repository.

## Uninstall

Exit Albert sessions and run `codex-albert stop` first. Then:

- Remove the installation directory (on Windows, `%LOCALAPPDATA%\Programs\CodexAlbertBridge` by default).
- Remove its `venv\Scripts` entry from your **user** PATH using Windows Environment Variables, if the installer added it.
- Delete only the bridge-managed `<profile>.config.toml` file and its private state directory if you also want to remove credentials and generated configuration.

Do not delete your whole `.codex` directory: it may contain unrelated Codex settings, authentication and conversations. Codex session history is managed separately from this bridge's state.

## Validation status

The initial portable package was tested on macOS with Python 3.12, LiteLLM 1.104.2 and the published Codex CLI 0.162.1. A real Albert session read a synthetic input, created a Python script with `apply_patch`, executed it and verified its output. No personal project content was needed for that test.

The installer also passed a syntax check with PowerShell 7.6.6 on macOS. The native Windows installation and DPAPI branch are included in a Windows GitHub Actions job. Local macOS validation cannot establish a successful Windows installation; check that CI job, or run the installer on a Windows machine, before treating native Windows support as fully validated. The workflow has not been run merely by creating it locally.
