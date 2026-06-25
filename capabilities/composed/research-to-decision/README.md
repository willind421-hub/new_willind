# Research To Decision

Composed capability slot for turning collected references into options,
evidence, tradeoffs, and user-facing recommendations.

## Autoresearch Boundary

`karpathy/autoresearch` is not treated as the primary engine for this capability.
It is a fixed-budget experiment loop reference, not a general web research tool.
This capability may hand off to `bounded-experiment-loop` only after research
has produced a clear target, metric, time/cost budget, and stop condition.

The reusable shape is:

1. define scope, metric, time budget, and stop condition
2. run small bounded attempts
3. compare each result against the metric
4. keep, discard, or defer with a reason
5. summarize decision-ready options

Willind uses `research-to-decision` for evidence collection, option narrowing,
and user-facing recommendations. It uses `bounded-experiment-loop` for
metric-based repeated improvement. Long-running execution, paid model calls,
browser login access, file edits, or external side effects must pass through
Permission Gate.

Source and adapter:

- imported source: `capabilities/imported/research/autoresearch`
- adapter contract: `capabilities/adapters/autoresearch`
- bounded experiment profile: `bounded_experiment_loop`
