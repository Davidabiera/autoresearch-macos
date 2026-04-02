# Second Mac Bootstrap Checklist — 2026-04-02

## Account And Workspace

- use the same ChatGPT Business owner account on the second Mac
- do not create a separate repo-specific subscription for the second machine
- in Workspace Settings, verify Codex access is enabled and GitHub app/plugin controls are enabled if GitHub-connected workflows are desired
- policy line for internal use:
  - OpenAI says Business inputs and outputs are not used by default to improve models: https://help.openai.com/en/articles/11369540/

## Questions For Your Folks

- who else, if anyone, needs a Business seat later
- whether anyone besides you will operate the second Mac
- whether GitHub integration is allowed in the Business workspace
- whether the second Mac can use the same macOS username and path convention

## Machine Prerequisites

- Apple Silicon Mac
- Command Line Tools and `git`
- Python `3.10`
- `uv`
- repo path must be `/Users/davidabiera/Projects/team/autoresearch-macos`

If the machine cannot use that path, stop and do not continue with launcher-based work until a shim or path refactor is chosen.

## Terminal Bootstrap

```bash
mkdir -p /Users/davidabiera/Projects/team
cd /Users/davidabiera/Projects/team
git clone https://github.com/Davidabiera/autoresearch-macos.git
cd autoresearch-macos
git remote rename origin github
git remote add origin https://github.com/miolini/autoresearch-macos.git
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
uv run prepare.py
git fetch --all
git worktree add -b codex/overnight-control worktrees/control github/codex/overnight-control
git worktree add -b codex/autoresearch-reliability worktrees/reliability github/codex/autoresearch-reliability
git worktree add -b codex/execution-baseline-mar10 worktrees/execution-baseline-mar10 github/codex/execution-baseline-mar10
```

## First Codex Session

- open the Business-backed Codex app
- start from `codex/overnight-control`
- read:
  - `AGENTS.md`
  - `README.md`
  - `program.md`
  - `control/docs/parallel_macos_bootstrap.md`
  - `control/docs/mar10_frontier_declaration_20260402.md`
  - `control/docs/parallel_macos_ramp_up_brief_20260402.md`
  - `control/docs/second_mac_kickoff_prompt.md`
- instantiate local `control/state/frontier.json` from the template plus the frontier declaration
- create the local handoff packet and triage board

## Acceptance Checks

- the second Mac can sign into the Codex app under the Business owner account
- the committed control docs pull cleanly
- `uv sync` completes
- `uv run prepare.py` completes, or the data cache is intentionally preseeded
- control, reliability, and execution-baseline worktrees exist and are clean
- the second Mac can state the canonical frontier branch, commit, trusted evidence, and next safe action without using chat memory
- no execution branch is owned by both machines
- no new experiment starts before one clean validation-oriented proof task completes
