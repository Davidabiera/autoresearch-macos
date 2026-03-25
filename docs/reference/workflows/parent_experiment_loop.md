# Parent Workflow: Autonomous Experiment Loop

## Purpose
Define the canonical parent-side workflow for `autoresearch-macos` when running the autonomous experiment loop with `experiment_reviewer` as a read-only adjudicator.

This workflow is the source of truth for:
- what the parent owns
- when the parent invokes `experiment_reviewer`
- how the parent interprets `keep`, `discard`, and `crash-rework`
- how `results.tsv` rows and learning entries are persisted
- when the loop may escalate as genuinely blocked

## Role Split
Parent owns:
- all file edits and git mutations
- branch state and frontier tracking
- experiment idea selection and one-line experiment descriptions
- run execution, timeout handling, and artifact collection
- reviewer invocation
- verdict application
- persistence of `results.tsv` rows and learning entries

`experiment_reviewer` owns:
- post-run adjudication only
- evidence-backed `keep` / `discard` / `crash-rework` decisions
- strict TSV row preparation or explicit blocked reason
- learning-entry generation for parent persistence

Operational invariant:
- Because `results.tsv` and the learning log are persisted in repo files, discard/crash rollback must revert only experiment-owned code surfaces, not hard-reset the whole worktree after persistence.

## Defaults Chosen
- Workflow style: prompt-driven execution with an explicit documented state machine
- Output style: human-readable decision packet with semi-structured fenced blocks; only the TSV row is machine-appendable
- Execution ownership: parent keeps all run execution and loop-state control
- `results.tsv`: initialize on setup if missing; treat as append-only run memory
- Run identity: assign `run_id` as `YYYYMMDD-HHMMSS_<branch>_<base_commit>`
- Per-run archive path: `logs/overnight/<branch>/<run_id>.log`
- Base commit: capture the current frontier commit before each new idea
- Crash-rework budget: allow at most 2 bounded rework attempts after the initial failed run for the same idea
- Blocked state: only for genuine workflow blockers, not ordinary ambiguity

## Required Inputs
- `program.md`
- `README.md`
- `prepare.py`
- `train.py`
- current branch name and `HEAD`
- `run.log` after each execution
- `results.tsv` when present
- learning log path: `docs/reference/agents/memory/experiment_reviewer_learning_log.md`

## State Machine

### 1. Setup
- Confirm the working branch is the intended experiment branch.
- Confirm `~/.cache/autoresearch/` contains required data/tokenizer artifacts.
- If `results.tsv` does not exist, create it with the header:
  `commit	val_bpb	memory_gb	status	description`
- Record `frontier_commit = HEAD`.
- Record whether this is a baseline run or a new experiment run.
  - If `results.tsv` has no prior rows beyond the header, the next run is the baseline run.
  - In that case, use `experiment_description = baseline`.

Transition:
- If setup is healthy, go to `Select Idea`.
- If cache/data is missing, enter `Blocked`.

### 2. Select Idea
- If this is the baseline run, make no code change and keep the current `train.py` as-is.
- Otherwise, choose exactly one bounded change to `train.py`.
- Write a one-line `experiment_description` suitable for the TSV description column.
- Record `base_commit = frontier_commit`.
- Reset `crash_rework_attempts = 0`.

Transition:
- Go to `Apply Change`.

### 3. Apply Change
- Skip this state for the baseline run.
- Otherwise edit `train.py` only.
- Keep the change bounded to the chosen idea.

Transition:
- Go to `Commit Candidate`.

### 4. Commit Candidate
- For the baseline run:
  - do not create a new commit
  - set `candidate_commit = base_commit`
- For any non-baseline run:
  - create a commit for the candidate change before execution
  - set `candidate_commit = HEAD`
- Record `run_id`.

Transition:
- Go to `Execute Run`.

### 5. Execute Run
- Run:
  `uv run train.py > run.log 2>&1`
- Enforce a hard 10-minute timeout.
- If the process exceeds 10 minutes, terminate it and treat the run as failed evidence.

Transition:
- Go to `Collect Evidence`.

### 6. Collect Evidence
- Inspect:
  - `grep "^val_bpb:\|^peak_vram_mb:" run.log`
  - `tail -n 50 run.log` when grep is empty or failure is suspected
- Archive:
  - copy the completed `run.log` to `logs/overnight/<branch>/<run_id>.log` before the next run starts
- Preserve:
  - branch name
  - `base_commit`
  - `candidate_commit`
  - `experiment_description`
  - `run_id`
  - whether `results.tsv` exists and whether it contains prior rows

Transition:
- Go to `Review Run`.

### 7. Review Run
- Invoke `experiment_reviewer` once per completed run using the canonical prompt in the next section.
- The reviewer response is valid only if it contains:
  - the six required sections
  - exactly one `RESULTS_TSV_ENTRY` or `RESULTS_TSV_BLOCKED` block
  - exactly one `LEARNING_LOG_ENTRY` block
- If the structure is malformed, ask the reviewer once to restate in the exact contract.

Transition:
- If the packet is valid, go to `Apply Verdict`.
- If still malformed after one retry, enter `Blocked`.

### 8. Apply Verdict

#### `keep`
- Append the reviewer-provided TSV row to `results.tsv`.
- Persist the reviewer-provided learning entry to `docs/reference/agents/memory/experiment_reviewer_learning_log.md`.
- Keep `candidate_commit` as the new frontier.
- Set `frontier_commit = candidate_commit`.
- Move to `Select Idea`.

#### `discard`
- Append the reviewer-provided TSV row to `results.tsv`.
- Persist the reviewer-provided learning entry to `docs/reference/agents/memory/experiment_reviewer_learning_log.md`.
- Restore `train.py` back to its `base_commit` version while preserving `results.tsv` and the learning log.
- Keep `frontier_commit = base_commit`.
- Move to `Select Idea`.

#### `crash-rework`
- Persist the reviewer-provided learning entry immediately to `docs/reference/agents/memory/experiment_reviewer_learning_log.md`.
- If `crash_rework_attempts < 2` and the fix is bounded:
  - increment `crash_rework_attempts`
  - keep the same `base_commit`
  - make only a local repair that preserves the experiment intent
  - create a new candidate commit
  - return to `Execute Run`
- Otherwise:
  - use the most recent reviewer-provided crash TSV row if present
  - append that crash row to `results.tsv`
  - restore `train.py` back to its `base_commit` version while preserving `results.tsv` and the learning log
  - keep `frontier_commit = base_commit`
  - move to `Select Idea`

Important rule:
- During an in-progress crash-rework path, do not append a TSV row yet unless the idea is being abandoned as a final crash.

#### Reviewer blocked payload
- If the reviewer returns `RESULTS_TSV_BLOCKED` for a completed run and the parent cannot recover the missing evidence locally, enter `Blocked`.

### 9. Blocked
The parent may escalate or stop only when the workflow is genuinely blocked, including:
- missing cache or tokenizer artifacts
- corrupted git state or inability to reset to `base_commit`
- inability to create commits
- malformed reviewer packet after one retry
- missing final crash TSV row when a crash-rework path is being abandoned
- missing or unreadable run artifacts that the parent cannot reconstruct

Ordinary ambiguity, low confidence, or mixed signals do not count as blocked if the reviewer returned an actionable verdict.

## Canonical Reviewer Invocation
Use this prompt shape when calling `experiment_reviewer`:

```text
Review one completed autoresearch-macos run and return the exact experiment_reviewer contract.

Run context:
- run_id: <run_id>
- branch: <branch>
- base_commit: <base_commit>
- candidate_commit: <candidate_commit>
- experiment_description: <one-line description>
- results_tsv_present: <yes/no>
- results_tsv_has_prior_rows: <yes/no>

Use these repo surfaces:
- program.md
- README.md
- current train.py
- current diff or last commit
- run.log
- results.tsv when present
- prepare.py only if needed to confirm fixed evaluation or time-budget constraints

Return exactly:
1. Run verdict summary
2. Adjudication
3. Evidence and rationale
4. Simplicity and platform-safety check
5. Logging payload
6. Next-step recommendation

Then include:
- exactly one fenced RESULTS_TSV_ENTRY or RESULTS_TSV_BLOCKED block
- exactly one fenced LEARNING_LOG_ENTRY block

Important:
- adjudicate only keep, discard, or crash-rework
- use a strict TSV row in RESULTS_TSV_ENTRY
- treat results.tsv as preferred context, not a hard prerequisite
- hard-check current macOS/MPS safety
- soft-flag broader portability drift when relevant
- do not edit files
```

## Persistence Rules
- `results.tsv` is append-only.
- The parent persists only reviewer-generated TSV rows, not ad hoc rows written from memory.
- The parent persists every `LEARNING_LOG_ENTRY` it receives to `docs/reference/agents/memory/experiment_reviewer_learning_log.md`.
- The parent must preserve the one-line `experiment_description` across crash-rework attempts for the same idea unless the idea is intentionally abandoned and replaced.
- After persisting a reviewer output, discard/crash rollback should restore experiment-owned code surfaces only. In the current repo that means `train.py`.
- The parent should preserve one archived raw log per completed run at `logs/overnight/<branch>/<run_id>.log`.

## Operational Notes
- Low reviewer confidence does not block the loop by itself if the verdict is actionable.
- The parent should prefer one clean experiment at a time over multi-idea edits.
- A crash-rework fix must stay within the same idea boundary. If the repair changes the research idea materially, abandon the crash and start a new idea from `Select Idea`.
