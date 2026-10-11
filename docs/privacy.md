# Privacy and publication

## What this repository contains

Only portable source code, public defaults, a generic assistant prompt, tests using dummy credentials, an installer, and documentation. The pre-existing license attribution and Git authorship are intentionally preserved.

The personal installation was not recursively copied. In particular, the repository excludes:

- Albert and local gateway keys;
- Codex authentication files, user preferences and project trust lists;
- user-specific model catalogs and custom instruction histories;
- session transcripts, benchmarks, screenshots and project contents;
- runtime logs, PID files, locks and installed environments;
- absolute paths identifying the original machine or user.

The model ID, public Albert endpoint, context limits and routing options are configuration data, not credentials. A new random local gateway key is generated at configuration time.

## Where secrets live

On Windows, credentials are encrypted with the operating system's Data Protection API (DPAPI), scoped to the current Windows account, in `credentials.dpapi`. The private state directory's inherited ACLs are removed and access is granted to the current user and SYSTEM. On macOS/Linux, credentials are plaintext JSON with owner-only permissions. These files remain outside the source checkout by default.

DPAPI does not protect against software already running as your Windows user, or an administrator who can access your account. It also means you cannot restore the encrypted file under an unrelated Windows account; enter the key again instead.

The key is obtained from a hidden prompt or `ALBERT_API_KEY`. It is passed only to the gateway's process environment, not in process arguments. The launcher removes bridge API-key environment variables before starting Codex. Your account can still read its own credential files; this project is not a security boundary against all local code.

## What leaves the computer

Your prompts, supplied file contents and tool outputs are sent to Albert when you run a model task. The bridge does not anonymize them. Do not confuse a publishable source repository with private inference: use Albert in accordance with your account and data policies.

The gateway binds only to `127.0.0.1`, requires its own bearer key, disables LiteLLM telemetry and normal message/spend logging, and does not install a startup service. Error logs can still contain sensitive context; treat the whole runtime directory as private. Codex has its own network behavior, plugin discovery, history and telemetry settings; the bridge does not disable all of them.

`status` calls the local gateway only. `doctor --check-api` calls Albert's model catalog but does not send a prompt or request a completion.

## Review before a push

The `.gitignore` excludes credentials, logs, transcripts, environments and `.codex` directories, but it is not a secret scanner. It also cannot remove secrets from existing Git history.

```sh
git status --short
git diff --cached --stat
git diff --cached
```

Review the complete staged diff. Look for keys, account identifiers, real home-directory paths and session data. Do not copy a generated private state directory into this repository or attach logs without reviewing them. Use generic paths and dummy values when writing examples.

If a key is accidentally published, revoke/rotate it with its issuer. Removing the current file alone does not erase earlier commits.
