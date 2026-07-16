# Workflow API and status contract

Use `../scripts/idea_workflow.py`; do not reproduce HTTP calls ad hoc unless debugging the client itself.

## Commands

| Command | Meaning | Success evidence |
|---|---|---|
| `health` | Read component health | JSON has `ok=true`; Provider degradation may remain |
| `start` | Create Case if needed and create immutable Run | JSON contains `run_id` and `QUEUED/RUNNING` |
| `status RUN_ID` | Read durable Run/Harness progress | JSON contains 11 persisted steps |
| `wait RUN_ID` | Poll until a terminal state | Returns terminal Run; timeout does not cancel backend |
| `report RUN_ID` | Read verified authoritative JSON | Succeeds only when report exists and Manifest verifies |
| `cancel RUN_ID` | Persist cancellation | JSON status is `CANCELLED` |
| `history` | List shared Cases | Returns durable local history |
| `run` | Start, wait, then fetch report | Final stdout is report JSON only on successful completion |

## Status meanings

- `QUEUED`: accepted but not yet executing.
- `RUNNING`: at least one Harness step is active or pending.
- `COMPLETED`: all 11 steps, audit gates, and Manifest passed without recorded limitations.
- `COMPLETED_WITH_LIMITATIONS`: all hard gates passed; limitations must be displayed.
- `FAILED`: attempt limit, critical audit, completion gate, or nonrecoverable contract error.
- `CANCELLED`: explicitly stopped; do not infer a final conclusion.

`start` is never proof that search happened. `wait` is never proof that a report exists unless the status is successful. `report` is the only final-output command.

## Recovery

A CLI wait timeout leaves the Run active as long as the backend process remains alive. Call `status` later with the same Run ID; do not create a duplicate Run merely because polling timed out.

API Tokens are intentionally not persisted. If the backend restarts, previously `QUEUED/RUNNING` Runs become `FAILED` with `RUNTIME_API_KEY_REQUIRED_AFTER_RESTART`. Supply the Token again and explicitly rerun; never recover from a credential file or silently reuse another user's Token.

## Error handling

- HTTP 422: invalid input or incoherent budget; correct parameters before retrying.
- HTTP 404: unknown Case/Run or report not yet available.
- HTTP 409: stored report failed integrity verification; do not bypass Manifest.
- API unavailable: the Workflow did not start unless a prior `start` returned a Run ID.
