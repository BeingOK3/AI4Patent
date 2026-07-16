# Input and adaptive budget

## Input quality

Prefer text that states the application scenario, objective technical problem, necessary structures or processing steps, relationships/order/conditions/data flow between those means, and claimed technical effect.

Do not add missing implementation details. The parser labels features as explicit, normalized, or inferred and copies exact source text for explicit features. The backend deterministically resolves and verifies Unicode offsets; a quote absent from the input remains a hard failure.

## Budget semantics

The candidate maximum limits merged summary-stage documents. It is not the number of full documents sent to a model.

The backend classifies the scope as narrow, medium, or broad using domain count, necessary features, and query specificity. It selects a deep-review target between the configured minimum and maximum:

- narrow: near the minimum;
- medium: midpoint;
- broad: near the maximum.

The minimum may never be below 10. A custom maximum must be at least the minimum, and the candidate maximum must cover the deep-review maximum.

## Cost control

All candidates are first screened using title, abstract/snippet, date, and term coverage. Only selected documents are fetched. The Document Analyzer receives a bounded evidence packet: claims, abstract, and relevant description spans. Full text is rebuildable FIFO cache data; cited evidence and hashes are durable.

Weak documents are never used to pad the count. If relevant/fetchable documents are below the minimum, the report records a limitation. Without a single destroying document, an under-minimum review cannot become a positive novelty conclusion.
