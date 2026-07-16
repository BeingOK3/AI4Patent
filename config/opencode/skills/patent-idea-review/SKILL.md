---
name: patent-idea-review
description: Run and present AI4Patent's durable patent IDEA workflow for novelty searches, inventive-step analysis, filing-value preassessment, simulated examination opinions, prior-art review, or questions such as whether a technical idea can be patented. Use for text, claim drafts, or technical proposals that need an auditable patent assessment; also use to inspect, resume, rerun, or explain an existing IDEA Run. Do not use the deprecated patent-IDEA-analyzer manual.
---

# Patent IDEA Review

Use the local Workflow API as the only execution authority. The backend, not this skill, controls search, document reading, evidence, conclusions, retries, history, and completion.

## Non-negotiable boundary

- Do not perform a parallel patent search yourself.
- Do not call EXA, Google Patents, web search, or fetch tools directly for an IDEA review.
- Do not simulate a tool result, evidence ID, Run status, or final report.
- Do not load the deprecated `patent-IDEA-analyzer` manual.
- Do not claim completion until the Run is terminal and `report` returns the stored `report.json`.
- If the local API is unavailable, report that execution did not start. Never fall back to an answer from model memory.

The backend always runs local Google Patents and EXA in its configured search layer, merges and deduplicates their results, and records independent Provider status. Either Provider may fail; the surviving Provider and FIFO cache may continue with an explicit limitation.

## Required input

Require a concrete technical proposal of at least 10 characters. Accept informal descriptions, claim drafts, or extracted document text. Preserve the user's technical relationships; do not silently add implementation details.

Use these defaults unless the user explicitly sets another value:

- evaluation date: current local date;
- date basis: `用户指定或提交日`;
- search mode: `standard`;
- candidate maximum: 80;
- deep-review minimum: 10;
- deep-review maximum: 20;
- scope: full novelty, inventive-step, and value review.

Read [input-and-budget.md](references/input-and-budget.md) only when the user asks how budgets are selected or supplies custom limits.

## Execute a new review

Locate `scripts/idea_workflow.py` relative to this Skill. Use the configured app URL, normally `http://127.0.0.1:8001`.

Before `start` or `run`, require the caller to provide the model API Token through `DEEPSEEK_API_KEY` (or a specifically named environment variable selected with `--api-key-env`). Never accept a literal key on the command line, print it, copy it into a report, or write it to a file. The CLI forwards it only to the Run creation request, and the backend holds it only in process memory for that Run.

1. Run `health`. Stop if the core service is unavailable.
2. Put long/multiline IDEA text in a temporary UTF-8 file. Do not store it in a log.
3. Run `start` with `--idea-file`, Case title, evaluation date, mode, and limits.
4. Capture the returned `run_id`. This proves submission only, not completion.
5. Run `wait RUN_ID`. The backend continues even if the conversation disconnects.
6. If terminal status is `COMPLETED` or `COMPLETED_WITH_LIMITATIONS`, run `report RUN_ID`.
7. Delete the temporary input file.
8. Present only values from the returned report.

Example commands:

```bash
python scripts/idea_workflow.py health
export DEEPSEEK_API_KEY='your-key'
python scripts/idea_workflow.py start --case-title "Token heat cache" --idea-file /tmp/idea.txt --mode standard --candidate-max 80 --deep-min 10 --deep-max 20
python scripts/idea_workflow.py wait RUN_ID --timeout 3600
python scripts/idea_workflow.py report RUN_ID
```

Use `run` instead of `start` + `wait` when the shell execution timeout safely covers the whole analysis. Read [workflow-api.md](references/workflow-api.md) when handling status, timeout, cancellation, rerun, or API errors.

## Existing Run

- For a Run ID, call `status RUN_ID` before answering.
- For a completed Run, call `report RUN_ID`; do not reconstruct the report from chat history.
- For a running Run, state the persisted current step and progress. Do not say “still working” without checking.
- For a failed Run, report its exact `error_code`, failed step, and attempt count. Do not complete the missing analysis yourself.
- For a cancelled Run, state that no final report exists unless the API actually returns one.

## Present the report

Lead with the stored Chinese novelty label:

- `NOVEL` → `具备新颖性`;
- `NOT_NOVEL` → `不具备新颖性`;
- `UNCERTAIN` → `新颖性结论不确定`.

Directly state `具备新颖性` when that is the audited result. Always include its confidence, closest document, missing features, search scope, Provider status, and limitations. Do not weaken it to “无法判断” merely because it is a model-assisted assessment.

Then summarize:

1. F1–Fn necessary features;
2. candidate and deep-review counts;
3. single-document novelty matrix;
4. each D1/D2 inventive-step route;
5. filing-value recommendation;
6. critical/warning audit counts;
7. material limitations and version provenance.

Never combine different documents to destroy novelty. Never turn `PARTIAL` into `DISCLOSED`. Never omit a Provider failure or a deep-review shortfall.

Read [evidence-and-conclusions.md](references/evidence-and-conclusions.md) when explaining why a conclusion is allowed or blocked. Read [report-fields.md](references/report-fields.md) when the user requests a field-by-field explanation or export mapping.

## Failure handling

- API unavailable: say no Run was created.
- `QUEUED`/`RUNNING`: provide Run ID and persisted progress; keep waiting if the user requested completion.
- `FAILED`: provide failed step, code, message, and attempts; suggest rerun only after explaining the failure.
- `CANCELLED`: do not restart without a new explicit request.
- report integrity error: state that Manifest verification failed; do not read files directly to bypass it.
- one Provider degraded: continue only through the backend and show the limitation.
- all Providers unavailable: do not claim that retrieval occurred.

The Workflow's terminal status and stored report are authoritative over any prose in this Skill.
