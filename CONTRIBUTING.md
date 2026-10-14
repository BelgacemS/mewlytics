# Contributing

The work follows the steps of [PLAN.md](PLAN.md), one step at a time.

## Git workflow

- `main` is stable. It is updated and tagged each time a grading level is reached (`v0.10.0`, `v0.12.0`, ..., `v1.0.0`).
- `dev` is the integration branch.
- Each step gets its own branch, `feat/<topic>` or `fix/<topic>`, created from `dev`. Tell your teammate before starting a step. A step whose dependencies are all checked can be done in parallel with another one.
- When the step is done and verified, check its box in `PLAN.md`, then commit on the step branch so that the commit includes `PLAN.md`.
- Merge into `dev` with `--no-ff`, then delete the step branch:

  ```sh
  git switch -c feat/<topic> dev
  # ... work, verify, check the box in PLAN.md ...
  git commit
  git switch dev
  git merge --no-ff feat/<topic>
  git branch -d feat/<topic>
  ```

- Pushing, and merging `dev` into `main`, happen only when both of us agree, not automatically after every step.
- Commit messages are short, in English, in the imperative mood, with no type prefix and no trailer. Examples: `Init repository`, `Add catalog read endpoints`, `Skip pairings without opponent`. Add a body only when it is really needed.
- Never commit secrets (`.env`, keys, certificates), data, run outputs or generated manifests. They are listed in `.gitignore`.

## Python environment

The repository is a [uv](https://docs.astral.sh/uv/) workspace: one `pyproject.toml` per service under `services/` and `libs/`, and a single `uv.lock` at the root. Python 3.12 is pinned in `.python-version`.

Install uv (macOS):

```sh
brew install uv
```

Create or update the environment with every workspace package and the dev tools (ruff, pytest):

```sh
uv sync --all-packages
```

Run tests and lint:

```sh
uv run --package <svc> pytest services/<svc>
uv run ruff check .
uv run ruff format --check .
```

Add dependencies:

```sh
uv add --package <svc> <dependency>   # runtime dependency of one service
uv add --dev <tool>                   # dev tool for the whole workspace
```

Run a command inside a service environment:

```sh
uv run --package <svc> <command>
```

Commit `pyproject.toml` and `uv.lock` together whenever dependencies change.
