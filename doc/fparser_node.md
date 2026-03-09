# fparser Node Structure

Reference for the fparser AST node system. Source: `fparser.two.utils` (base
classes) and `fparser.two.Fortran2003` (~426 grammar classes).

## Core architecture

Every fparser node is an instance of `Base` or one of its ~16 specialized
subclasses. The class hierarchy is shallow (2–4 levels), but wide: ~426
concrete grammar classes instantiate these base types.

```
Base
├── BlockBase                 # content list — block constructs
├── SequenceBase              # items tuple + separator — delimited lists
├── UnaryOpBase               # items: (op, rhs)
├── BinaryOpBase              # items: (lhs, op, rhs)
├── SeparatorBase             # items: (lhs?, rhs?) — colon-separated
├── KeywordValueBase          # items: (key?, value)
├── BracketBase               # items: (left, inner?, right)
├── NumberBase                # items: (value, kind?)
├── CallBase                  # items: (designator, args?)
│   └── CALLBase              #   uppercase variant
├── StringBase                # string attr — leaf token
│   └── STRINGBase            #   uppercase variant
├── StmtBase                  # items — statement with label/name
│   ├── EndStmtBase           #   END [type [name]]
│   └── Type_Declaration_StmtBase  # type [, attrs ::] entities
└── WORDClsBase               # items: (keyword, clause?)
```

## Two child-storage mechanisms

| Mechanism | Attribute | Type | Used by | Semantics |
|-----------|-----------|------|---------|-----------|
| **items** | `self.items` | `tuple` (immutable) | All except BlockBase | Fixed-arity, positional slots |
| **content** | `self.content` | `list` (mutable) | BlockBase only | Variable-length statement sequence |

The `children` property (on `Base`) unifies them:

```python
@property
def children(self):
    child_list = getattr(self, "content", None)
    if child_list is None:
        child_list = getattr(self, "items", [])
    return child_list
```

StringBase is a special case: it stores data in `self.string`, not in `items`
or `content`. `children` returns `[]` for these nodes.


## The match → init pipeline

Parsing a node follows a fixed protocol:

```
cls(string)          # calls __new__
  → cls.match(string)       # static method, returns tuple or None
  → obj = object.__new__(cls)
  → _set_parent(obj, result)  # wire parent refs on children
  → obj.init(*result)       # unpack tuple into items/content/string
```

`match()` is the parser. It returns a tuple whose structure is dictated by the
base class (see table below). `init()` stores that tuple. `tostr()` inverts
`match()` — it reconstructs the source text from the stored structure.


## Base class reference

### Base

The root class. Direct subclasses in Fortran2003.py (~175 classes) implement
custom `match()` methods that return ad-hoc tuples.

| Attribute | Type | Set by |
|-----------|------|--------|
| `items` | `tuple` | `init(*result)` |
| `parent` | `Base \| None` | `_set_parent()` during parsing |
| `string` | `str` | `__new__` — the original source text |
| `item` | `readfortran.Line` | `__new__` — carries label, name, span info |

Direct-Base classes are the most heterogeneous: each defines its own `items`
layout. This is where the bulk of the schema-registry work will be.


### BlockBase

Block constructs: `DO...END DO`, `IF...END IF`, derived type definitions, etc.
~33 classes.

```
match(startcls, subclasses, endcls, reader) → (content_list,)
init(content)  → self.content = content
```

`content` is a flat list: `[start_stmt, body_item, ..., end_stmt]`.

`tofortran()` joins content with newlines, indenting body items by 2 spaces
when the block ends with an `EndStmtBase`.

```python
# Example: Do_Construct.content
[Nonlabel_Do_Stmt, Assignment_Stmt, Assignment_Stmt, End_Do_Stmt]
```


### SequenceBase

Separator-delimited lists. ~4 classes.

```
match(separator, subcls, string) → (separator, (item1, item2, ...))
init(separator, items) → self.separator = separator; self.items = items
```

| Slot | Content |
|------|---------|
| `separator` | `str` — `","`, `"%"`, etc. |
| `items` | `tuple` of homogeneous child nodes |

`tostr()` joins items with formatted separator (adds spaces around operators,
space after comma).


### UnaryOpBase

Prefix unary operators: `-x`, `.NOT. y`. ~3 classes.

```
match(op_pattern, rhs_cls, string) → (op_str, rhs_obj)
```

| Slot | Content |
|------|---------|
| `items[0]` | operator string |
| `items[1]` | RHS node |


### BinaryOpBase

Infix binary operators: `a + b`, `x .AND. y`. ~17 classes.

```
match(lhs_cls, op_pattern, rhs_cls, string, right=True) → (lhs, op, rhs)
```

| Slot | Content |
|------|---------|
| `items[0]` | LHS node |
| `items[1]` | operator string |
| `items[2]` | RHS node |

`right=True` means split at rightmost operator (left-associative parsing).


### SeparatorBase

Colon-separated ranges: `1:10`, `:n`, `m:`. ~8 classes.

```
match(lhs_cls, rhs_cls, string) → (lhs_or_None, rhs_or_None)
```

| Slot | Content |
|------|---------|
| `items[0]` | LHS node or `None` |
| `items[1]` | RHS node or `None` |


### KeywordValueBase

Keyword-value pairs: `FMT='(A10)'`, `UNIT=6`. ~13 classes.

```
match(lhs_cls, rhs_cls, string) → (key_or_None, value)
```

| Slot | Content |
|------|---------|
| `items[0]` | keyword node/string or `None` |
| `items[1]` | value node |


### BracketBase

Bracketed expressions: `(expr)`, `[array]`, `(/.../)`. ~6 classes.

```
match(brackets, cls, string) → (left_str, inner_or_None, right_str)
```

| Slot | Content |
|------|---------|
| `items[0]` | left bracket string |
| `items[1]` | inner node or `None` |
| `items[2]` | right bracket string |


### NumberBase

Numeric literals with optional kind: `42`, `3.14_REAL64`. ~6 classes.

```
match(number_pattern, string) → (value_str_upper, kind_or_None)
```

| Slot | Content |
|------|---------|
| `items[0]` | number string (uppercased) |
| `items[1]` | kind parameter string or `None` |


### CallBase / CALLBase

Function calls, array subscripts: `f(x)`, `arr(i, j)`. ~19 classes.

```
match(lhs_cls, rhs_cls, string) → (designator, args_or_None)
```

| Slot | Content |
|------|---------|
| `items[0]` | LHS node (function/array name) |
| `items[1]` | RHS node (argument list) or `None` |

`CALLBase` is identical but uppercases the LHS during matching.


### StringBase / STRINGBase

Leaf tokens that match a literal string or regex. Not decomposed further.

```
match(pattern, string) → (matched_str,)
init(string) → self.string = string   # NOT self.items
```

`STRINGBase` uppercases before matching. Used for Fortran keywords
(`SEQUENCE`, `PRIVATE`, `PUBLIC`, etc.). ~21 classes.

**Important**: these nodes use `self.string`, not `self.items`. The `children`
property returns `[]` for them.


### StmtBase

Statements with optional label and construct name. ~51 classes.

`StmtBase` itself does not change `items` layout — subclasses define their own
`match()`. The contribution is in `tofortran()`, which prepends the label and
construct name from `self.item` (the `readfortran.Line` object):

```
[ label ] [ construct-name : ] stmt-text
```


### EndStmtBase

END statements: `END`, `END PROGRAM`, `END SUBROUTINE foo`. ~15 classes.

```
match(stmt_type, stmt_name, string) → (type_str_or_None, name_or_None)
```

| Slot | Content |
|------|---------|
| `items[0]` | statement type string (`"PROGRAM"`, `"DO"`, ...) or `None` |
| `items[1]` | name node or `None` |


### WORDClsBase

Keyword followed by optional clause: `IMPORT :: a, b`. ~1 class in Fortran2003.

```
match(keyword, cls, string, colons=False) → (keyword_str, clause_or_None)
```

| Slot | Content |
|------|---------|
| `items[0]` | keyword string |
| `items[1]` | clause node or `None` |


### Type_Declaration_StmtBase

Type declarations: `INTEGER, INTENT(IN) :: x, y`. ~2 classes.

```
match(type_cls, attr_cls, entity_cls, string) → (type, attrs_or_None, entities)
```

| Slot | Content |
|------|---------|
| `items[0]` | type-spec node |
| `items[1]` | attribute-spec-list node or `None` |
| `items[2]` | entity-decl-list node |


## Class-level metadata

Every grammar class declares two class attributes:

### `subclass_names: list[str]`

Classes this node can **delegate to** via polymorphic dispatch. When
`cls.match()` returns `None`, fparser tries each class in `subclass_names`.

This models **union types** (abstract grammar rules):

```python
class Program_Unit(Base):
    subclass_names = [
        "Comment", "Main_Program", "External_Subprogram",
        "Function_Subprogram", "Subroutine_Subprogram", "Module", ...
    ]
```

### `use_names: list[str]`

Classes that may appear as **children** in the parse tree. Used by the parser
to register classes for name lookup.

```python
class Specification_Part(BlockBase):
    use_names = [
        "Use_Stmt", "Import_Stmt",
        "Implicit_Part", "Declaration_Construct"
    ]
```

Together, `subclass_names` models IS-A relationships (vertical dispatch) and
`use_names` models HAS-A relationships (horizontal composition).


## Parent tracking

`_set_parent(parent_node, items)` is called in `Base.__new__()` after
`match()` succeeds. It recursively walks the result tuple/list and sets
`.parent` on every `Base` instance found:

```python
def _set_parent(parent_node, items):
    for item in items:
        if isinstance(item, Base):
            item.parent = parent_node
        elif isinstance(item, (list, tuple)):
            _set_parent(parent_node, item)
```

Only immediate children get `parent` set to the node. Deeper descendants
retain their own parent from when they were parsed. Navigate upward with
`node.parent` or `node.get_root()`.


## Source reconstruction

Two methods:

| Method | Purpose |
|--------|---------|
| `tostr()` | Reconstruct the node's text (no indentation) |
| `tofortran(tab, isfix)` | Reconstruct with indentation and label handling |

`__str__` calls `tostr()`. Each base class defines `tostr()` to invert its
`match()`:

- `BinaryOpBase.tostr()` → `"{lhs} {op} {rhs}"`
- `CallBase.tostr()` → `"{designator}({args})"`
- `BlockBase.tofortran()` → newline-joined content with body indentation

The `tostr()`/`tofortran()` methods are the ground truth for the CST → text
path (via fparser as intermediary).


## Traversal

```python
def walk(node_list, types=None):
    """Depth-first traversal. Returns list of nodes matching types."""
```

Uses the `children` property, so it works uniformly across `items` and
`content` nodes.


## Implications for the CST converter

The converter must handle three distinct patterns:

1. **items-based nodes** (~393 classes): map positional `items[i]` to named
   edges. Each base class defines the slot semantics (see tables above).
   Direct-Base subclasses need per-class schemas.

2. **content-based nodes** (~33 BlockBase classes): map `content` list to
   container edges with a shared field name.

3. **string-based nodes** (~21 StringBase/STRINGBase classes): map to leaf
   `Node` with `value = self.string`.

The `items` entries can be:
- `Base` instances → child `Node`
- `str` values → leaf `Node` with value
- `None` → omitted (optional slot not present)
- Nested `tuple`/`list` → must be flattened or mapped per schema
