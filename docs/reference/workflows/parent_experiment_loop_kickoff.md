# Kickoff Prompt: Parent Experiment Loop

Use this in a fresh parent session when you want to run the autonomous loop with `experiment_reviewer`.

```text
Read these files first:
- docs/reference/workflows/parent_experiment_loop.md
- AGENTS.md
- program.md
- README.md
- prepare.py
- train.py

You are the parent agent for autoresearch-macos.

Own all repo mutations and loop state:
- choose one bounded experiment at a time
- edit only train.py
- commit before execution
- run `uv run train.py > run.log 2>&1`
- enforce the 10-minute timeout rule
- invoke experiment_reviewer after every completed run using the canonical contract in the workflow doc
- apply keep, discard, and crash-rework exactly as defined there
- persist reviewer-provided TSV rows to results.tsv
- persist reviewer-provided LEARNING_LOG_ENTRY blocks to `docs/reference/agents/memory/experiment_reviewer_learning_log.md`

Defaults:
- results.tsv should exist with the canonical header before the loop runs
- treat results.tsv as append-only memory
- keep execution with the parent; use experiment_reviewer only as a read-only adjudicator
- if results.tsv has no prior rows, the next run is the baseline run and should use the current train.py unchanged
- do not ask whether to continue once the loop starts unless the workflow reaches Blocked state

Start by reporting:
- current branch
- current HEAD
- whether cache/data artifacts exist
- whether results.tsv exists and has prior rows
- whether the next run is baseline or a new experiment

Then proceed according to the parent workflow doc.
```
