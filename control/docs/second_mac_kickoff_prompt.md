# Kickoff Prompt: Second Mac Codex

Use this in a fresh Codex session on the second Mac after the repo is cloned cleanly.

```text
Read these files first:
- AGENTS.md
- README.md
- program.md
- control/docs/parallel_macos_bootstrap.md
- control/docs/mar10_frontier_declaration_20260402.md
- control/docs/parallel_macos_ramp_up_brief_20260402.md
- control/docs/second_mac_bootstrap_checklist_20260402.md
- control/state/frontier.json if it exists, otherwise control/docs/frontier_ledger_template.json
- control/docs/handoff_packet_template.md
- control/docs/triage_board_template.md

You are not starting a fresh research repo. You are joining an existing multi-lane autoresearch-macos system.

Operating rules:
- treat control/state/frontier.json as the canonical frontier truth
- if `control/state/frontier.json` does not exist yet, rebuild it from `control/docs/mar10_frontier_declaration_20260402.md` plus `control/docs/frontier_ledger_template.json`
- do not infer the frontier from chat history, local notes, or raw logs
- do not mutate branches you do not own
- do not run free exploration until the second Mac has passed one clean bootstrap-validation proof
- keep raw runtime artifacts local unless asked to distill them into reports
- update tracked handoff and triage surfaces when your role changes or your run state changes

Your first task is orientation, not experimentation.

Report these fields before taking action:
- assigned machine name
- assigned role
- assigned branch
- assigned worktree path
- frontier branch from the ledger
- frontier commit from the ledger
- trust status from the ledger
- active queue from the ledger
- next safe action from the ledger
- any ambiguity or missing field that blocks safe execution

Then do exactly this:
1. Verify the assigned branch matches your role.
2. Verify the branch is clean except for allowed runtime artifacts.
3. Verify the queue or plan you were assigned actually exists.
4. Verify your work does not overlap another machine's ownership.
5. Stay in validation or confirmation scope until the second Mac bootstrap is proven clean.
6. Only after that proof, and only if your role changes, may you move to one bounded exploratory queue.
7. Update the handoff packet and triage board before starting long-running work.

If any of these are ambiguous, stop and repair the control surfaces first.

Do not:
- start from scratch
- create a new canonical frontier on your own
- run two concurrent loops against the same execution branch
- treat a single strong number as trusted without the current gate context

Start by summarizing:
- what role you own
- what branch you own
- what evidence you are trusting
- what the next safe action is
```
