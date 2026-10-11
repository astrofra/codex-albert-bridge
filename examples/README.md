# Public configuration examples

These files show the complete generated profile, LiteLLM routing, and one-model catalog using public defaults. They contain no credentials or machine-specific paths.

Use `codex-albert configure` to create working copies outside the repository. Do not manually copy this directory into your Codex home: `<PYTHON_EXECUTABLE>` and `<BRIDGE_STATE_DIR>` are illustrative placeholders, and the authentication helper depends on the installed Python package.

The model catalog uses the generic prompt in `src/codex_albert_bridge/data/instructions.md`. The generator in `config.py` is the source of truth when changing models or budgets.
