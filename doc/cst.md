# CST Node Model — Design Notes

## Problem

fparser produces a Fortran AST using ~426 concrete classes derived from ~16
base classes.  The class hierarchy encodes structural information (binary op
vs block vs sequence) implicitly through inheritance and ad-hoc attribute
conventions (`items` tuple, `content` list, `string` attribute).

This makes uniform traversal, pattern matching, and transformation difficult:
every consumer must know the class hierarchy to interpret child positions.

## Design

Replace the heterogeneous class hierarchy with three frozen Pydantic models:

```
Span   — source location
Edge   — labeled link from parent to child
Node   — the tree node
```

### Node

| Field  | Type                | Meaning                                  |
|--------|---------------------|------------------------------------------|
| kind   | str                 | Constructor tag (maps to fparser class)   |
| value  | str \| None         | Literal text for leaf/token nodes         |
| span   | Span \| None        | Half-open byte offset [start, end)        |
| edges  | tuple[Edge, ...]    | Ordered children                          |

Invariant: a node is **either** a leaf (`value` set, `edges` empty) **or** an
interior node (`value` is None, `edges` non-empty).  Enforced by a Pydantic
model validator.

### Edge

| Field      | Type | Meaning                         |
|------------|------|---------------------------------|
| field_name | str  | Semantic role of the child      |
| child      | Node | The child node                  |

### Span

| Field | Type | Meaning                  |
|-------|------|--------------------------|
| start | int  | Byte offset, inclusive   |
| end   | int  | Byte offset, exclusive   |


## Two modes of a node

Every interior node is one of two kinds, determined by its edge pattern:

### Structured node

Each edge has a **distinct** `field_name`.  The edges form named slots.

```
Node(kind="Add_Operand")
  ├── Edge(field_name="lhs")  → Node(kind="Name", value="x")
  ├── Edge(field_name="op")   → Node(kind="Op",   value="+")
  └── Edge(field_name="rhs")  → Node(kind="Name", value="y")
```

Access: `node.child("lhs")` — returns the single child, raises if duplicates.

Maps to fparser's `items` tuple, where each position has a fixed role
(e.g. `BinaryOpBase.items = (lhs, op, rhs)`).

### Container node

Edges **share** a `field_name`.  Order is given by position in the tuple.

```
Node(kind="Block")
  ├── Edge(field_name="stmt") → Node(kind="Assignment_Stmt", ...)
  ├── Edge(field_name="stmt") → Node(kind="Assignment_Stmt", ...)
  └── Edge(field_name="stmt") → Node(kind="Print_Stmt", ...)
```

Access: `node.children("stmt")` — returns ordered tuple of all matches.

Maps to fparser's `content` list (variable-length, homogeneous role).

The mode is **implicit** — determined by usage, not by a flag on the node.
Since `kind` is the fparser class name (derived via `type(node).__name__`),
the mode for any `kind` can be determined dynamically by inspecting the
fparser class via `getattr(Fortran2003, kind)` — no static registry needed.


## Bidirectional navigation

In memory, every node and edge holds a reference to its parent.  These
references are **excluded from serialization**.

```
Node._parent  → Edge | None    (the edge pointing to this node)
Edge._parent  → Node | None    (the node owning this edge)
```

Implemented as Pydantic `PrivateAttr` fields:

- Excluded from `model_dump()`, `model_dump_json()`, and JSON schema.
- Wired in `model_post_init`, which runs both on construction and on
  deserialization — so parent links are always present in memory and always
  absent on the wire.

Wiring order (bottom-up, follows natural construction):

1. Leaf `Node` created — `_parent = None`.
2. `Edge` created with that child — `Edge.model_post_init` sets
   `child._parent = self`.
3. Parent `Node` created with edges — `Node.model_post_init` sets
   `edge._parent = self`.

Navigation properties on `Node`:

| Property      | Type          | Meaning                              |
|---------------|---------------|--------------------------------------|
| `parent`      | Node \| None  | Parent node (skips the edge)         |
| `parent_edge` | Edge \| None  | The incoming edge (carries role info) |
| `is_root`     | bool          | True when `_parent is None`          |


## Immutability

All three models use `frozen=True`.  Trees are persistent data structures —
edits produce new trees.  This makes nodes safe to hash and share across
analyses.

`edges` is `tuple[Edge, ...]` (not `list`) to reinforce this: the children
sequence is itself immutable and hashable.


## Converter architecture

Three representations are interconvertible:

```
Layer 2:   CST  (Node + Edge)
             ↕  ast_to_cst / cst_to_ast
Layer 1:   fparser AST (426 classes)
             ↕  str_to_ast / ast_to_str
Layer 0:   Fortran source text
```

Six functions in three files, each file named after its **target**:

| File | Function | Signature | Status |
|------|----------|-----------|--------|
| `to_cst.py` | `ast_to_cst` | `(Base) -> Node` | implemented |
| `to_cst.py` | `str_to_cst` | `(str) -> Node` | implemented (composes) |
| `to_fparser.py` | `str_to_ast` | `(str) -> Base` | implemented |
| `to_fparser.py` | `cst_to_ast` | `(Node) -> Base` | not yet implemented |
| `to_text.py` | `ast_to_str` | `(Base) -> str` | implemented |
| `to_text.py` | `cst_to_str` | `(Node) -> str` | not yet implemented |

Composed paths (`str_to_cst`, `cst_to_str`) are one-liners that chain the
two atomic converters.  `cst_to_ast` (and therefore `cst_to_str`) can
reconstruct fparser classes via `getattr(Fortran2003, node.kind)` — the
`kind` string is the class name by construction.

### ast_to_cst dispatch

`ast_to_cst` dispatches on the fparser node's structural base class via
`match`/`case`.  Each base class has a dedicated handler in `handlers.py`
that knows the fixed slot semantics:

| Base class | Edge names | Mode |
|---|---|---|
| BlockBase | `"stmt"` | container |
| SequenceBase | `"item"` | container |
| BinaryOpBase | `lhs`, `op`, `rhs` | structured |
| UnaryOpBase | `op`, `operand` | structured |
| SeparatorBase | `lower`, `upper` | structured |
| KeywordValueBase | `keyword`, `value` | structured |
| BracketBase | `left`, `content`, `right` | structured |
| NumberBase | `value`, `kind` | structured |
| CallBase | `designator`, `args` | structured |
| EndStmtBase | `type`, `name` | structured |
| WORDClsBase | `keyword`, `clause` | structured |
| Type_Declaration_StmtBase | `typespec`, `attrs`, `entities` | structured |
| StringBase | (leaf — `value` set) | token |
| Base (fallback) | `item_0`, `item_1`, ... | positional |

Match-case order is critical: more specific classes (EndStmtBase,
Type_Declaration_StmtBase) must precede their parents in the MRO.  Nodes
with multiple inheritance (e.g. `Assignment_Stmt` is both `StmtBase` and
`BinaryOpBase`) match the structural base class first.

The generic fallback uses positional edge names (`item_0`, `item_1`, ...)
so every fparser tree is convertible immediately.  Semantic edge names for
the ~175 direct-Base subclasses can be added incrementally — the fparser
class is always recoverable via `getattr(Fortran2003, kind)`.

### Sentinel node kinds

The generic fallback introduces two internal sentinel kinds to preserve
the full positional structure of fparser's ``items`` tuples:

| Kind | Meaning |
|------|---------|
| `__absent__` | Marks a `None` slot in the items tuple (empty optional). |
| `__list__` | Wraps a nested list/tuple found in items; children are positional edges (`item_0`, `item_1`, …). |

These sentinels ensure the reverse converter (`cst_to_ast`) can reconstruct
items tuples with the correct length and nesting.  They appear **only**
inside generic-fallback nodes, never inside structured-handler output.


### cst_to_ast dispatch

`cst_to_ast` mirrors `ast_to_cst`: it resolves the fparser class via
`getattr(Fortran2003, node.kind)`, determines the structural base class
with `issubclass`, and reconstructs `items` / `content` / `string`.
For structured base classes the reverse mapping is hardcoded (same field
names as the forward handler).  For the generic fallback, positional edges
are converted back to an items tuple via `_to_item`.


## Source files

```
src/fcst/
├── cst.py                      # Node, Edge, Span
└── converters/
    ├── __init__.py              # re-exports all six functions
    ├── to_cst.py                # ast_to_cst, str_to_cst
    ├── to_fparser.py            # str_to_ast, cst_to_ast
    ├── to_text.py               # ast_to_str, cst_to_str
    └── handlers.py              # per-base-class conversion handlers
```
