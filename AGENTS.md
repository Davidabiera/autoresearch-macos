## Custom Agent Routing: experiment_reviewer

Use `experiment_reviewer` when:
- a run has completed and `run.log` plus a current diff or last commit are ready for judgment
- the parent needs a keep, discard, or crash-rework verdict on a completed change
- the parent needs a structured TSV recommendation or validation

Do not use `experiment_reviewer` when:
- the task is to edit `train.py`
- the task is broad repo mapping, docs verification, or long-range experiment planning

Feed it:
- `run.log`
- `results.tsv` when present
- the current diff or last commit
- current `train.py`
- `program.md` and `README.md`

Expect it to return:
- a clear `keep`, `discard`, or `crash-rework` verdict
- evidence-backed rationale
- a structured TSV logging payload
- one next-step recommendation
- one `LEARNING_LOG_ENTRY` block for parent persistence

Spawn only from:
- a trusted repo session with standard approvals and normal posture
