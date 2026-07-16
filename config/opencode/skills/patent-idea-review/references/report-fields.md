# Authoritative report fields

`report.json` is authoritative; `report.md` is a deterministic readable rendering.

| Field | Use |
|---|---|
| `conclusion_overview` | Stored Chinese novelty label, confidence, route statuses, filing recommendation |
| `idea_features` | F1–Fn text, required flag, source type/span |
| `evaluation` | evaluation date, basis, and scope |
| `search_execution` | query/call/hit/candidate/deep-review counts |
| `provider_status` | independent call, success, failure, and result counts |
| `candidate_documents` | deduplicated summary-stage candidates and provenance |
| `deep_review_documents` | reviewed metadata and F1–Fn mappings |
| `novelty` | single-document matrices, closest/destroying document, missing features, rationale |
| `inventiveness` | bounded D1/D2 routes and distinction evidence |
| `value_assessment` | detectability, workaround, technical/market value as 1–5 scores, alternatives, recommendation |
| `simulated_office_action` | model-assisted narrative based only on frozen facts |
| `audit` | deterministic and advisory findings/counts |
| `limitations` | Provider, count, evidence, and analysis limitations |
| `provenance` | model, Skill, Workflow, and configuration versions |

The report endpoint verifies `manifest.json` before returning content. Do not open report files directly to work around an HTTP 409.

When summarizing, keep patent numbers, dates, counts, feature statuses, and conclusions exact. Narrative text must never override structured fields.
