# Evidence and conclusion rules

## Evidence states

- `DISCLOSED`: the supplied quote supports the complete feature.
- `PARTIAL`: the quote supports only part of the feature.
- `NOT_DISCLOSED`: the document has a definite gap for that feature.
- `UNCERTAIN`: available text cannot support a definite mapping.

`DISCLOSED` and `PARTIAL` require a real evidence ID bound to the same Run and document. The auditor verifies quote SHA-256, document ownership, publication date, and durable matrix equality.

## Novelty

Novelty uses the single-document principle. One document destroys novelty only if that same document maps every necessary F1–Fn to `DISCLOSED`. Features from different documents are never combined.

The report may directly state `具备新颖性` when no reviewed single document discloses every necessary feature, every reviewed document has a definite `NOT_DISCLOSED` gap, the configured deep-review minimum was met, and all date/evidence/audit/Manifest gates passed.

Give the reason, confidence, closest document, missing features, scope, Provider state, and limitations. This is an assessment within the recorded search scope, not an absolute worldwide guarantee.

## Inventive step

Each route has one D1. Its distinguishing features may use bounded D2 candidates from other reviewed documents. `NOT_INVENTIVE` requires, for every distinction, at least one fully `DISCLOSED` D2 teaching, bound evidence IDs, and a supported motivation to combine.

Otherwise use the route's stored `INVENTIVE`, `UNCERTAIN`, or `NEED_MORE_EVIDENCE`. Do not invent another D2 outside the report.

## Audit authority

Only deterministic date/hash/ownership/matrix failures create Workflow-blocking critical findings. Semantic auditor findings are advisory warnings, even if the model proposed a critical severity.
