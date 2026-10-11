# Configuration and architecture

## Request flow

Codex talks to the loopback gateway using the Responses API. LiteLLM 1.104.2 translates requests, streaming responses, tool calls, and usage counters to/from Albert's OpenAI-compatible Chat Completions API. `use_chat_completions_api: true` is required because this integration does not use an Albert Responses endpoint.

The launcher starts LiteLLM on demand. A file lock serializes concurrent starts. Health checks authenticate with a separate random local gateway key. Before stopping a process, the launcher checks both its creation time and its configuration path to avoid killing an unrelated process after PID reuse.

The launcher invokes Codex with `--no-daemon --profile albert-bridge`. It does not change approval or sandbox settings. Those remain Codex's responsibility. No ChatGPT or OpenAI key is bundled with this project; model requests use your Albert credentials.

## Public data and generated files

The package ships two small, public files under `src/codex_albert_bridge/data`:

- `defaults.json`: model ID, endpoint, port and token budgets;
- `instructions.md`: a short, generic coding-assistant prompt written for this project.

It generates a single-model `models.json` instead of copying a personal Codex model catalog. The generated instructions deliberately differ from the original machine's extensive instructions; benchmark behavior may differ.

| Local file | Contents |
| --- | --- |
| `settings.json` | Model, budgets, port, executable path and Codex home; no keys. |
| `proxy.yaml` | LiteLLM routing; keys referenced through environment variables. |
| `models.json` | One-model Codex catalog and generic instructions. |
| `credentials.dpapi` (Windows) | Both keys encrypted for the current Windows account. |
| `credentials.json` (macOS/Linux) | Both keys in an owner-only plaintext file. |
| `proxy.log` | Private gateway diagnostics. |
| `proxy.pid.json`, `startup.lock` | Local process state. |
| `<profile>.config.toml`, in Codex home | Dedicated model/provider settings and authentication helper. |

The auth helper uses the installation's Python executable, `-m codex_albert_bridge`, and the absolute private state directory. Paths containing spaces are represented as argument arrays, not interpolated shell commands. Windows uses the native Codex executable rather than passing user prompts through `cmd.exe`.

## Change a setting

Stop the gateway, then regenerate all related files together:

```sh
codex-albert stop
codex-albert configure --port 8420
codex-albert doctor --check-api
codex-albert
```

Press Enter at the key prompt to retain the saved key. New values take effect when the gateway and a new Codex session start. Editing generated files by hand is possible, but the next `configure` overwrites them.

For another Albert model, use the exact model ID and context length from its catalog. Check tool calling support and set its output budget explicitly:

```sh
codex-albert configure --model MODEL_ID --context-window 131072 --max-completion-tokens 32768 --headroom-tokens 16384
```

The example budgets are those of the default model, not a claim that every Albert model supports them. No fallback model is configured.

The compaction threshold is calculated as:

```text
context window - maximum completion - headroom
131072         - 32768              - 16384 = 81920
```

Changing only a model's display metadata does not set its generation cap. The generator keeps the request limit, catalog and profile aligned. Sampling settings such as temperature and top-p are left to Albert's defaults; Qwen-specific overrides are not applied to DeepSeek.

`--api-base` supports another HTTPS endpoint, but sends your Albert key to that endpoint. Change it only when intentionally configuring a trusted, compatible service.

## Keep installations separate

The default profile name is `albert-bridge`, so it does not replace an existing `albert` profile. An existing unmanaged profile is not overwritten. `configure --profile NAME --codex-home PATH` selects another profile and Codex home. Set `ALBERT_BRIDGE_HOME` consistently when using several installations, and give each a different port and profile.

The default Codex user configuration is inherited. Disabled app connectors do not disable arbitrary user-configured MCP servers, plugins, hooks or skill instructions. Use a separate `--codex-home` when you need a clean test environment.

## Reference

- [OpenAI: profile files and configuration precedence](https://learn.chatgpt.com/docs/config-file/config-advanced)
- [OpenAI: configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
- [OpenAI: Codex CLI](https://learn.chatgpt.com/docs/cli)
- [LiteLLM proxy documentation](https://docs.litellm.ai/docs/simple_proxy)
- [Albert API](https://albert.api.etalab.gouv.fr/)
