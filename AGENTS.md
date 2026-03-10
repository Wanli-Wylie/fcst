# fcst — Fortran Concrete Syntax Tree

A Python library that wraps fparser's Fortran AST into a simplified, uniform
tree representation with labeled edges and bidirectional navigation.

## Current Stage: Public API for Simplified AST

The scope of this stage is a complete, tested, public-facing API for:

1. **Unified node model** — Three frozen Pydantic models (`Node`, `Edge`,
   `Span`) replace fparser's ~426 concrete classes. Every node has a
   consistent interface; parent-child relationships are typed, labeled edges.

2. **Six converter functions** — Lossless conversion between three
   representations (Fortran text, fparser AST, fcst CST):

   ```
   Layer 2:   CST  (Node + Edge)
                ↕  ast_to_cst / cst_to_ast
   Layer 1:   fparser AST (426 classes)
                ↕  str_to_ast / ast_to_str
   Layer 0:   Fortran source text
   ```

3. **Fragment parsing** — `parse_as(text, kind)` parses a text fragment
   using a specific grammar production, returning a CST subtree.

4. **Public `__init__.py`** — Exports `Node`, `Edge`, `Span`, all converter
   functions, and `parse_as`.

### Deliverables

| Component | File | Status |
|-----------|------|--------|
| `Node`, `Edge`, `Span` | `cst.py` | Done |
| `ast_to_cst` | `converters/to_cst.py` | Done |
| `str_to_cst` | `converters/to_cst.py` | Done |
| `str_to_ast` | `converters/to_fparser.py` | Done |
| `ast_to_str` | `converters/to_text.py` | Done |
| `cst_to_ast` | `converters/to_fparser.py` | Done |
| `cst_to_str` | `converters/to_text.py` | Done |
| `parse_as` | `converters/to_cst.py` | Done |
| Public API in `__init__.py` | `__init__.py` | Done |
| Tests | `tests/` | Done (27 passing) |

### Done when

- All six converters implemented and passing
- Round-trip property: `cst_to_str(str_to_cst(src))` reproduces the same
  text as `ast_to_str(str_to_ast(src))` for a corpus of Fortran programs
- `parse_as` works for common grammar productions
- Public API exports are clean and documented

## Stack

- Python 3.10+
- Build: uv
- Upstream parser: fparser

## Design Docs

| Doc | Scope |
|-----|-------|
| `doc/cst.md` | Node model, edge modes, converter architecture, dispatch table |
| `doc/fparser_node.md` | Reference for fparser's base class hierarchy and slot semantics |

## TODO: Analysis Framework

Design specs for future semantic analysis live in `doc/todo/`:

| Doc | Content |
|-----|---------|
| `doc/todo/semantic_resolution.md` | Two-pass resolution (per-file + project-wide) |
| `doc/todo/local_analysis_passes.md` | 12 local analysis passes with dependency graph |

These require the converter layer to be solid and tested first.
