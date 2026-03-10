# [TODO] Local Analysis Passes — Dependency and Parallelism

> **Status: TODO** — Design spec for the analysis framework stage.
> Not in scope for the current stage (public API for simplified AST).

## The twelve analyses

Within a single Fortran file, the following semantic analyses enrich the CST.
Each is a **read-only visitor** over the immutable Node tree, producing
results into its own **annotation side table** (a `dict` keyed by node
identity).

| # | Analysis | Output |
|---|----------|--------|
| 1 | Scope tree construction | Tree of scoping units (program, module, function, block) |
| 2 | IMPLICIT rule resolution | Per-scope implicit typing map (letter → type) |
| 3 | Declaration collection | Per-scope list of explicitly declared symbols |
| 4 | USE import cataloging | Per-scope list of stub symbols (name, module, alias) |
| 5 | Symbol table construction | Per-scope name → symbol map (joins 2 + 3 + 4) |
| 6 | Host association resolution | Per-internal-subprogram set of visible host symbols |
| 7 | Type resolution | Full resolved type for each symbol |
| 8 | Expression typing | Resolved type for each expression node |
| 9 | Call/array disambiguation | Classification of each `a(i)` as array access or call |
| 10 | Interface resolution | Generic call → specific procedure mapping |
| 11 | Constant folding | Compile-time values for PARAMETERs, bounds, kind values |
| 12 | Control flow annotation | Loop nesting, branch structure, label targets |


## Dependency graph

An arrow A → B means "A requires B's output."

```
                    ┌─────┐
                    │  1  │  Scope tree
                    └──┬──┘
              ┌───────┬┼┬───────┐
              ▼       ▼ ▼       ▼
           ┌─────┐ ┌─────┐ ┌─────┐ ┌──────┐
           │  2  │ │  3  │ │  4  │ │  12  │
           └──┬──┘ └──┬──┘ └──┬──┘ └──────┘
              │       │       │      (independent)
              └───────┼───────┘
                      ▼
                   ┌─────┐
                   │  5  │  Symbol table
                   └──┬──┘
                 ┌────┴────┐
                 ▼         ▼
              ┌─────┐  ┌──────┐
              │  6  │  │  11  │
              └──┬──┘  └──┬───┘
                 │        │
                 └───┬────┘
                     ▼
                  ┌─────┐
                  │  7  │  Type resolution
                  └──┬──┘
                ┌────┴────┐
                ▼         ▼
             ┌─────┐  ┌─────┐
             │  8  │  │  9  │
             └──┬──┘  └──┬──┘
                └────┬────┘
                     ▼
                  ┌──────┐
                  │  10  │  Interface resolution
                  └──────┘
```

### Dependency matrix

| Analysis | Requires |
|----------|----------|
| 1. Scope tree | Parse tree only |
| 2. IMPLICIT rules | 1 (scope nesting for host → internal propagation) |
| 3. Declarations | 1 (scope assignment for each declaration) |
| 4. USE imports | 1 (scope to attach stubs to) |
| 5. Symbol table | 2, 3, 4 (combines all three into per-scope map) |
| 6. Host association | 5 (needs complete symbol tables for host and internal scopes) |
| 7. Type resolution | 5, 6, 11 (symbols + host-visible symbols + evaluated constants) |
| 8. Expression typing | 7 (needs resolved type of every operand) |
| 9. Call/array disambig | 7 (needs symbol kind — array vs function — and type info) |
| 10. Interface resolution | 8, 9 (needs typed arguments to select specific procedure) |
| 11. Constant folding | 5 (needs PARAMETER values and kind values from symbol table) |
| 12. Control flow | 1 (structural only — no semantic dependencies) |


## Parallelism groups

Topological sort by dependency level. Analyses within the same stage are
independent and can run in parallel over the same immutable tree.

```
Stage 0:  [ 1 ]              Scope tree
Stage 1:  [ 2, 3, 4, 12 ]   IMPLICIT + Declarations + USE + Control flow
Stage 2:  [ 5 ]              Symbol table  (join of 2, 3, 4)
Stage 3:  [ 6, 11 ]          Host association + Constant folding
Stage 4:  [ 7 ]              Type resolution
Stage 5:  [ 8, 9 ]           Expression typing + Call/array disambiguation
Stage 6:  [ 10 ]             Interface resolution
```

**Critical path:** 7 stages, but the practical pipeline is shorter because
stages 2–4 are tightly coupled (real compilers interleave them).

**Within-stage parallelism:**  At stages 1, 3, and 5, the listed analyses
read disjoint information from the tree and write to separate side tables.
No synchronization is required.

**Cross-scope parallelism:**  Once stage 4 (type resolution) completes for
a module's specification part, expression typing (stage 5) can proceed
independently for each contained subprogram.  This is the same insight that
Fortran build systems exploit: `.mod` files first, then compile procedures
in parallel.


## Annotation side tables

The immutable CST (`Node` with `frozen=True`) is shared across all passes.
Each analysis writes to its own external dictionary:

```python
SideTable[T] = dict[int, T]   # id(node) → annotation
```

This gives:
- **No mutation** of the tree — analyses are pure functions.
- **No synchronization** between independent analyses — each writes to its
  own table.
- **Composable results** — downstream analyses read from upstream side tables,
  not from mutated tree nodes.

A pass is a function:

```
pass(tree: Node, *upstream_tables) → SideTable[T]
```

It walks the tree, reads from upstream side tables where needed, and produces
a new side table.


## Two known circularities

### Constant folding ↔ Type resolution

Array bounds and kind parameters are specification expressions that must be
folded to constants.  But folding them requires knowing operand types.

**Resolution (from LFortran and Flang):**  Interleave constant folding with
declaration processing.  When a declaration is encountered, evaluate its
specification expressions immediately using whatever is already in the symbol
table.  This makes constant folding incremental within stage 2–4 rather than
a separate stage.

For fcst: stages 2–4 can be fused into a single "specification resolution"
pass that processes declarations in source order, building the symbol table
and folding constants as it goes.

### Call/array disambiguation ↔ Symbol table

The parser cannot distinguish `a(i)` syntactically.  Resolving it requires
the symbol table.  But statement functions (a legacy feature) create symbols
that look like array assignments at parse time.

**Resolution (from Flang):**  Parse optimistically, build the symbol table
from the specification part, then rewrite the parse tree to fix mis-parses.
For fcst: since the CST is immutable, disambiguation is an annotation (not
a rewrite) — the side table records whether each `a(i)` node is an array
access or a function call.


## Mapping to real compilers

### LFortran (2 passes)

| Pass | Analyses covered |
|------|------------------|
| SymbolTableVisitor | 1, 2, 3, 4, 5, 6, 11 (specification expressions) |
| BodyVisitor | 7 (completion), 8, 9, 10, 12 |

### Flang (4 sub-phases within ResolveNames)

| Sub-phase | Analyses covered |
|-----------|------------------|
| ResolveSpecificationParts | 1, 2, 3, 4, 5, 6 |
| FinishSpecificationParts | 7, 11 (specification expressions) |
| ResolveExecutionParts | 8, 9 |
| FinishExecutionParts | 10, deferred checks |

Both compilers effectively collapse stages 0–4 into a single specification
pass, then run stages 5–6 as a body pass.


## Recommended architecture for fcst

### Batch mode (near term)

Two passes, matching the LFortran / Flang split:

**Specification pass** (stages 0–4 fused):  Walk the CST top-down through
specification parts only.  Build scope tree, collect declarations, resolve
IMPLICIT rules, catalog USE imports, construct symbol tables, resolve host
association, fold constants, resolve types.  Produces five side tables:
scope, symbols, types, constants, host-association.

**Body pass** (stages 5–6, parallelizable per subprogram):  Walk executable
statement bodies.  Type expressions, disambiguate calls/arrays, resolve
generic interfaces, annotate control flow.  Each subprogram can be processed
independently once its scope's specification pass is complete.

```
CST (immutable, shared)
  │
  ├─ Specification pass ──→ [scope, symbols, types, constants, host-assoc]
  │
  └─ Body pass (per subprogram, parallel) ──→ [expr-types, disambig, interfaces, control-flow]
```

### Incremental mode (future)

If fcst evolves toward IDE integration, the Salsa/rust-analyzer model
applies:

- Each analysis becomes a memoized query in a dependency graph.
- File edits invalidate only affected queries.
- Early cutoff: if a re-parsed file produces the same specification summary,
  body-level analyses for other files are not re-run.
- Per-function granularity: editing a function body invalidates only that
  function's body-pass results, not the specification pass.

This is not needed for batch analysis but is the natural evolution if
real-time annotation is desired.
