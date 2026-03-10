"""Converters targeting the fparser AST representation.

- str_to_ast : Fortran text  → fparser AST
- cst_to_ast : CST           → fparser AST
"""

from __future__ import annotations

from fparser.common.readfortran import FortranStringReader
from fparser.two import Fortran2003 as _f03
from fparser.two.parser import ParserFactory
from fparser.two.utils import (
    Base,
    BinaryOpBase,
    BlockBase,
    BracketBase,
    CallBase,
    EndStmtBase,
    KeywordValueBase,
    NumberBase,
    SeparatorBase,
    SequenceBase,
    StringBase,
    Type_Declaration_StmtBase,
    UnaryOpBase,
    WORDClsBase,
)

from fcst.cst import Node

# Cache parser instances per standard — ParserFactory().create() is expensive.
_parsers: dict[str, type] = {}


def _get_parser(std: str) -> type:
    if std not in _parsers:
        _parsers[std] = ParserFactory().create(std=std)
    return _parsers[std]


def str_to_ast(source: str, std: str = "f2003") -> Base:
    """Parse Fortran source text into an fparser AST.

    *std* selects the Fortran standard (``"f2003"``, ``"f2008"``).
    """
    parser = _get_parser(std)
    reader = FortranStringReader(source)
    return parser(reader)


# ------------------------------------------------------------------
# cst_to_ast helpers
# ------------------------------------------------------------------


def _to_item(node: Node):
    """Convert a CST child node to an fparser item (Base, str, list, or None)."""
    if node.kind == "token":
        return node.value
    if node.kind == "__absent__":
        return None
    if node.kind == "__list__":
        return [_to_item(e.child) for e in node.edges]
    return cst_to_ast(node)


def _slot(node: Node, field_name: str) -> Base | str | None:
    """Get an optional named edge's fparser item, or None if absent."""
    for e in node.edges:
        if e.field_name == field_name:
            return _to_item(e.child)
    return None


def _wire_parents(parent: Base, children: tuple | list) -> None:
    """Set .parent on fparser child nodes (mirrors fparser._set_parent)."""
    for child in children:
        if isinstance(child, Base):
            child.parent = parent
        elif isinstance(child, (list, tuple)):
            _wire_parents(parent, child)


def _make_node(cls: type) -> Base:
    """Create a bare fparser node, bypassing the parser."""
    obj = object.__new__(cls)
    obj.parent = None
    obj.item = None
    return obj


def _set_items(obj: Base, items: tuple) -> None:
    """Set items on a node and wire parent refs."""
    obj.items = items
    _wire_parents(obj, items)


def _reconstruct_generic_items(node: Node) -> tuple:
    """Rebuild items tuple from positional edges.

    The forward ``convert_generic`` preserves all slots (including Nones
    as ``__absent__``), so edges are in order and we can simply convert
    each child back via ``_to_item``.
    """
    return tuple(_to_item(e.child) for e in node.edges)


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def cst_to_ast(node: Node) -> Base:
    """Convert a CST Node (and all descendants) back to an fparser AST.

    Dispatch mirrors :func:`~fcst.converters.to_cst.ast_to_cst`: resolves
    the fparser class from ``node.kind``, determines the structural base
    class, and reconstructs ``items`` / ``content`` / ``string``.
    """
    cls = getattr(_f03, node.kind, None)
    if cls is None:
        raise ValueError(f"Unknown fparser class: {node.kind!r}")

    obj = _make_node(cls)

    # --- Leaf: StringBase (self.string) ---
    if issubclass(cls, StringBase):
        obj.string = node.value
        return obj

    # --- Container: BlockBase (self.content) ---
    if issubclass(cls, BlockBase):
        obj.content = [_to_item(c) for c in node.children("stmt")]
        _wire_parents(obj, obj.content)
        return obj

    # --- Container: SequenceBase (self.separator + self.items) ---
    if issubclass(cls, SequenceBase):
        obj.separator = ","
        obj.items = tuple(_to_item(c) for c in node.children("item"))
        _wire_parents(obj, obj.items)
        return obj

    # --- Structured: specific base classes (most-specific first) ---
    if issubclass(cls, EndStmtBase):
        _set_items(obj, (_slot(node, "type"), _slot(node, "name")))
    elif issubclass(cls, Type_Declaration_StmtBase):
        _set_items(obj, (
            _slot(node, "typespec"),
            _slot(node, "attrs"),
            _slot(node, "entities"),
        ))
    elif issubclass(cls, BinaryOpBase):
        _set_items(obj, (
            _slot(node, "lhs"),
            _slot(node, "op"),
            _slot(node, "rhs"),
        ))
    elif issubclass(cls, UnaryOpBase):
        _set_items(obj, (_slot(node, "op"), _slot(node, "operand")))
    elif issubclass(cls, SeparatorBase):
        _set_items(obj, (_slot(node, "lower"), _slot(node, "upper")))
    elif issubclass(cls, KeywordValueBase):
        _set_items(obj, (_slot(node, "keyword"), _slot(node, "value")))
    elif issubclass(cls, BracketBase):
        _set_items(obj, (
            _slot(node, "left"),
            _slot(node, "content"),
            _slot(node, "right"),
        ))
    elif issubclass(cls, NumberBase):
        _set_items(obj, (_slot(node, "value"), _slot(node, "kind")))
    elif issubclass(cls, CallBase):
        _set_items(obj, (_slot(node, "designator"), _slot(node, "args")))
    elif issubclass(cls, WORDClsBase):
        _set_items(obj, (_slot(node, "keyword"), _slot(node, "clause")))
    else:
        # --- Generic fallback ---
        if node.is_leaf and node.value is not None:
            obj.string = node.value
            return obj
        if node.edges:
            items = _reconstruct_generic_items(node)
            _set_items(obj, items)
        else:
            obj.items = ()

    return obj
