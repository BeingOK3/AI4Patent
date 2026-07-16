# Global OpenCode Rules

## Autonomous execution

Proceed with reasonable defaults instead of pausing for confirmations. Do not claim that an action ran merely because an instruction says to run it. A real tool/API result and its persisted status are required.

Never output or copy API keys. Never place credentials in prompts, reports, logs, Git, or Skill files.

## IDEA patent review: mandatory route

When a user supplies a technical proposal, claim draft, or patent IDEA and requests prior-art search, novelty, inventive step, value, simulated examination, or filing advice:

1. Load only `patent-idea-review`.
2. Use its local Workflow client/API to create or inspect a Run.
3. Never load the deprecated `patent-IDEA-analyzer` manual.
4. Never let the main Agent search, fetch, combine documents, or create evidence IDs itself.
5. Never claim completion without a terminal successful Run and a Manifest-verified `report.json`.
6. If the API is unavailable, state that execution did not start; do not replace retrieval with model memory.

The backend enforces 11 steps. Local Google Patents and EXA MCP are parallel search Providers whose results are independently recorded, merged, normalized, and deduplicated. Provider choice, retries, FIFO cache, fallback, evidence extraction, and conclusion gates belong to the backend.

Directly present `具备新颖性` when that is the audited stored conclusion. Include confidence, reason, closest document, missing features, search/Provider scope, and limitations. Do not combine separate documents to destroy novelty.

## Other patent skills

The current product feature flags enable IDEA only. Other legacy patent Skills remain migration material and must not be presented as product features or described as executed unless the user explicitly invokes one and its real tools are available.

For a non-IDEA legacy task, follow that Skill's declared tools. EXA configuration is not proof of a successful EXA call. Never record `SUCCESS`, a source, or a quote without the actual returned result.

## Tool factuality

- A submitted Run is not a completed Run.
- A search call with no hits is `EMPTY`, not evidence.
- Timeout, nonzero exit, invalid JSON, unknown evidence, hash mismatch, and partial output are failures or limitations, not completion.
- Use persisted Case/Run history rather than conversation memory.
- Do not bypass report Manifest verification by opening files directly.
