# fcst — Fortran Concrete Syntax Tree

A Python library that enhances fparser's Fortran AST into a richer concrete syntax tree with unified node representation and contextual semantic annotations.

## Goals

1. **Unified node abstraction** — Reduce fparser's type system complexity (hundreds of classes in a deep inheritance hierarchy) by introducing a uniform representation: every node has a consistent interface, and parent-child relationships are modeled as typed, labeled edges rather than ad-hoc class attributes.

2. **Contextual annotations** — Attach semantic context to the syntax tree: symbol binding (which declaration does this name refer to?), scope links (which scope is this node in?), and type information. This lifts the tree from a pure AST toward a CST that downstream analyses can consume directly.

## Stack

- Python 3.10+
- Build: uv
- Upstream parser: fparser 
