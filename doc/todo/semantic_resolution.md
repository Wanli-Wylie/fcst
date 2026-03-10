# [TODO] Two-Pass Semantic Resolution

> **Status: TODO** — Design spec for the analysis framework stage.
> Not in scope for the current stage (public API for simplified AST).

## Problem

Fortran's module system means a single file rarely contains enough information
to fully resolve all semantic references.  `USE some_module` imports symbols
whose types, signatures, and definitions live in another file.  A tool that
insists on full resolution (like LFortran's ASR) must process the entire
project and reject anything incomplete.

fcst takes a different stance: **resolve what you can, mark what you can't,
never fail.**  A partially-annotated CST is strictly more useful than no
annotations at all.


## Design: two passes, monotonic refinement

```
Pass 1 (per-file)                    Pass 2 (project-wide)
─────────────────                    ─────────────────────
Parse file → CST                     Collect all Pass 1 results
Build file-local scope tree          Build global module table
Resolve locally-declared symbols     Fill in USE stub symbols
Create stubs for USE imports         Disambiguate remaining a(i)
Partial disambiguation of a(i)       Connect submodules to parents
                                     Verify COMMON block consistency
```

Each pass only **adds** information — symbols go from `Unresolved` to
`Resolved`, never the reverse.  This is the monotonic refinement pattern:
resolution state only grows.


## Pass 1: what is resolvable within a single file

### Fully resolvable

| Category | Rationale |
|----------|-----------|
| Local variable declarations | All locals are declared in the same scoping unit |
| Module-level declarations | A module's own variables, types, parameters, procedures are in the file |
| IMPLICIT typing | IMPLICIT rules are scoping-unit-local; default rules are known |
| Internal subprograms (CONTAINS) | Always in the same file as their host |
| Host association | Nested subprograms access host scope, which is in the same file |
| Intrinsic procedures | Fixed, known signatures; can be resolved from a built-in table |
| Inline interface blocks | Interface body defines the full signature in the file |

### Partially resolvable (names known, details unknown)

| Category | What Pass 1 knows | What requires Pass 2 |
|----------|-------------------|---------------------|
| USE statements | Module name, imported names, aliases, provenance | Types, signatures, definitions of imported symbols |
| EXTERNAL declarations | Name is an external procedure | Signature (unless an interface block is also present) |
| Generic interfaces (cross-module) | The interface exists and names the specifics | Specifics imported via USE need their signatures |
| Derived type members (cross-module) | `x` has type `TYPE(foo)` | Components of `foo` if imported via USE |
| Array vs function ambiguity | Resolved when the declaration is local | Unresolved when the symbol is imported |

### Not resolvable without external files

| Category | Reason |
|----------|--------|
| INCLUDE files | Textual insertion from another file (though fparser may resolve these during lexing) |
| Submodule ↔ parent connection | Inherently cross-file by design |
| COMMON block consistency | Layout agreement is a cross-file property |


## The unresolved symbol pattern

When Pass 1 encounters a USE-imported name whose definition is unavailable,
it creates a **stub symbol** — a placeholder that records everything known
from the local file and explicitly marks what is unknown.

Three patterns from other language toolchains:

| Pattern | Tool | Behavior |
|---------|------|----------|
| Error type with candidates | Roslyn (C#) | `IErrorTypeSymbol` implements the full type interface but has `TypeKind.Error`. Stores best-guess candidates and rejection reasons. Downstream code never sees null. |
| Top-type widening | TypeScript | Failed resolution produces `any` (the most permissive type). Downstream checking succeeds trivially. Diagnostics are emitted only at the resolution site. |
| Value + error accumulation | rust-analyzer | Every query returns `(T, Vec<Error>)`. The value may contain unresolved markers. Errors are collected, not thrown. Analysis always completes. |

For fcst, the rust-analyzer pattern fits best: every annotation query produces
a result (possibly partial) plus diagnostics.  The CST is always valid and
navigable; unresolved references are first-class markers, not error states.

A stub symbol should carry:

- The name as it appears in the USE statement
- The source module name
- Any alias (local rename)
- A resolution status: `Unresolved` / `Resolved`
- When resolved: the full symbol information (type, kind, signature, etc.)


## Pass 2: project-wide resolution

Pass 2 operates on the **collection** of all Pass 1 results.  It builds a
global module table and resolves cross-file references.

### Algorithm

1. **Collect module exports.**  For each file, extract the module's public
   symbol table (names, types, interfaces) from its Pass 1 result.

2. **Build global module table.**  Map module names to their export tables.
   This is the Fortran equivalent of rust-analyzer's `DefMap` or fortls's
   `obj_tree`.

3. **Resolve USE stubs.**  For each unresolved USE import, look up the
   module in the global table.  Replace the stub with the resolved symbol.
   If the module is not found, the stub remains with a diagnostic.

4. **Cascade resolution.**  Resolving a USE import may enable further
   resolution: a derived type member access that was blocked by an unknown
   type can now proceed; an `a(i)` ambiguity that depended on the imported
   symbol's kind can now be disambiguated.

5. **Handle dependency order.**  Modules can USE other modules.  Process in
   topological order of the USE dependency graph.  Circular USE dependencies
   are illegal in Fortran (the standard forbids them), so the graph is a DAG.

### What gets resolved

- USE stub symbols → full type/signature/definition
- `a(i)` ambiguity → array element access or function call
- Derived type member access → verified against type definition
- Generic procedure calls → resolved to specific procedure
- Submodule → connected to parent module interface
- COMMON block → cross-file layout consistency check


## Prior art

### fortls (Fortran Language Server)

Regex-based parser.  Maintains per-file `FortranFile` objects and a global
`obj_tree` mapping symbol names to definitions.  Two-phase: parse all files
in parallel, then resolve cross-references via the global table.  Incremental
updates re-parse changed files and re-resolve affected scopes.

Limitation: regex parsing cannot handle complex Fortran syntax.  Unresolved
references simply fail to navigate (no error-symbol pattern).  No
demand-driven computation — all resolution is eager.

### LFortran

Strictly two-pass within a file (SymbolTableVisitor, then BodyVisitor), with
full resolution required.  Cross-file via `.mod` files.  Any unresolved
symbol is a hard error — ASR is valid-by-construction.

This is the opposite of fcst's philosophy: LFortran rejects partial
information; fcst embraces it.

### Flang (LLVM)

Seven-pass semantic analysis pipeline.  Processes files in dependency order.
Cross-module resolution via `.mod` files (stripped-down Fortran source
containing public symbols).  Same-file modules are processed in order without
`.mod` files.

### Roslyn (C#)

Immutable `Compilation` snapshots.  `IErrorTypeSymbol` propagates through the
type graph without halting analysis.  Red-Green trees for incremental
reparsing.  The most mature implementation of partial resolution in a
production compiler.

### rust-analyzer

Salsa-powered demand-driven computation.  `DefMap` built by fixed-point
iteration over unresolved imports.  Every query returns `(T, Vec<Error>)`.
Editing a function body does not invalidate cross-module resolution
(ItemTree stability).  The most applicable architectural model for fcst's
future incremental analysis.


## Implications for fcst

### Near term

Pass 1 is sufficient for the current goal: enrich the CST with file-local
semantic annotations (scope tree, local symbol table, implicit resolution,
host association).  This is useful standalone — it enables navigation,
rename, go-to-definition for locally-defined symbols.

### Future

Pass 2 requires:

1. A **module export format** — a serializable summary of each file's public
   symbols (the equivalent of a `.mod` file, but as a Python data structure).
2. A **global resolution algorithm** — topological traversal of the USE
   dependency DAG, filling in stubs.
3. An **incremental strategy** — when a file changes, determine which
   downstream files need re-resolution (the inverse dependency graph).

The Salsa pattern (demand-driven, memoized queries with early cutoff) is the
ideal long-term architecture but is not needed initially.  A simpler
"parse all, resolve all" batch mode is sufficient to validate the design.
