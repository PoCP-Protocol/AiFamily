# design_copilot

Design-time capabilities for the IPD/PDM/PLM product factory. This package is
provider-neutral and side-effect free: it validates product drafts before
Human Gate review and never writes business facts.

## Current capability

`compiler.py` provides a deterministic `ProductCompiler` with twelve checks:

1. schema
2. component
3. compatibility
4. workflow
5. resource
6. AI use case
7. context boundary
8. safety
9. Human Gate
10. cost
11. evaluation
12. SLA

The compiler receives an immutable `CompilerContext`/`CompilerCatalog` and
returns a read-only `CompilerReport`. Missing catalog entries, malformed
inputs, and check exceptions fail closed. It does not call a model/provider,
repository, or business command, and a passing report is evidence for Human
Gate review rather than approval itself.

## Web boundary

The Web Product Factory accepts an optional server `compiler_report` on a
DRAFT response and renders it through the read-only `CompilerReportPanel`.
The panel preserves the twelve-check order and blocks Human Gate messaging
when the report is incomplete or failed. It never advances lifecycle state or
writes facts.

## Deferred capabilities

- `simulation.py` remains a guarded simulation seam; simulated evidence cannot
  self-promote to pilot.
- Runtime catalog loading and Product Factory route composition are owned by
  the application composition root and are not performed in this package.
- Model execution remains behind `backend/intelligence/model_gateway` and is
  outside the deterministic compiler.
