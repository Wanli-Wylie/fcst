"""Per-base-class handlers for fparser AST → CST conversion.

Each handler knows the fixed slot semantics of its base class and produces
edges with proper field names.  The ``recurse`` callback points back to
:func:`~fcst.converters.to_cst.ast_to_cst` for child conversion.
"""

from __future__ import annotations

from typing import Any, Callable

from fparser.two.utils import Base

from fcst.cst import Edge, Node

Recurse = Callable[[Base], Node]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _kind(node: Base) -> str:
    """Derive the CST ``kind`` from the fparser class name."""
    return type(node).__name__


def _item_to_node(item: Any, recurse: Recurse) -> Node | None:
    """Convert one element of an fparser ``items`` tuple to a CST Node.

    Returns None for absent optional slots (``None`` items).
    """
    if item is None:
        return None
    if isinstance(item, Base):
        return recurse(item)
    if isinstance(item, str):
        return Node(kind="token", value=item)
    raise TypeError(f"Unexpected item type: {type(item)!r}")


def _edges(
    names: tuple[str, ...],
    items: tuple | list,
    recurse: Recurse,
) -> tuple[Edge, ...]:
    """Zip *names* with *items*, converting each item and skipping Nones."""
    result: list[Edge] = []
    for name, item in zip(names, items):
        child = _item_to_node(item, recurse)
        if child is not None:
            result.append(Edge(field_name=name, child=child))
    return tuple(result)


# ------------------------------------------------------------------
# Base-class handlers
# ------------------------------------------------------------------


def convert_block(node: Any, recurse: Recurse) -> Node:
    """BlockBase: ``content`` list → container edges."""
    edges: list[Edge] = []
    for child in node.content:
        cst_child = _item_to_node(child, recurse)
        if cst_child is not None:
            edges.append(Edge(field_name="stmt", child=cst_child))
    return Node(kind=_kind(node), edges=tuple(edges))


def convert_sequence(node: Any, recurse: Recurse) -> Node:
    """SequenceBase: ``items`` tuple → container edges."""
    edges: list[Edge] = []
    for child in node.items:
        cst_child = _item_to_node(child, recurse)
        if cst_child is not None:
            edges.append(Edge(field_name="item", child=cst_child))
    return Node(kind=_kind(node), edges=tuple(edges))


def convert_binary_op(node: Any, recurse: Recurse) -> Node:
    """BinaryOpBase: ``(lhs, op, rhs)``."""
    return Node(
        kind=_kind(node),
        edges=_edges(("lhs", "op", "rhs"), node.items, recurse),
    )


def convert_unary_op(node: Any, recurse: Recurse) -> Node:
    """UnaryOpBase: ``(op, operand)``."""
    return Node(
        kind=_kind(node),
        edges=_edges(("op", "operand"), node.items, recurse),
    )


def convert_separator(node: Any, recurse: Recurse) -> Node:
    """SeparatorBase: ``(lower?, upper?)``."""
    return Node(
        kind=_kind(node),
        edges=_edges(("lower", "upper"), node.items, recurse),
    )


def convert_keyword_value(node: Any, recurse: Recurse) -> Node:
    """KeywordValueBase: ``(keyword?, value)``."""
    return Node(
        kind=_kind(node),
        edges=_edges(("keyword", "value"), node.items, recurse),
    )


def convert_bracket(node: Any, recurse: Recurse) -> Node:
    """BracketBase: ``(left, content?, right)``."""
    return Node(
        kind=_kind(node),
        edges=_edges(("left", "content", "right"), node.items, recurse),
    )


def convert_number(node: Any, recurse: Recurse) -> Node:
    """NumberBase: ``(value, kind?)``."""
    return Node(
        kind=_kind(node),
        edges=_edges(("value", "kind"), node.items, recurse),
    )


def convert_call(node: Any, recurse: Recurse) -> Node:
    """CallBase / CALLBase: ``(designator, args?)``."""
    return Node(
        kind=_kind(node),
        edges=_edges(("designator", "args"), node.items, recurse),
    )


def convert_string(node: Any) -> Node:
    """StringBase / STRINGBase: leaf with ``self.string``."""
    return Node(kind=_kind(node), value=node.string)


def convert_end_stmt(node: Any, recurse: Recurse) -> Node:
    """EndStmtBase: ``(type?, name?)``."""
    return Node(
        kind=_kind(node),
        edges=_edges(("type", "name"), node.items, recurse),
    )


def convert_word_cls(node: Any, recurse: Recurse) -> Node:
    """WORDClsBase: ``(keyword, clause?)``."""
    return Node(
        kind=_kind(node),
        edges=_edges(("keyword", "clause"), node.items, recurse),
    )


def convert_type_decl_stmt(node: Any, recurse: Recurse) -> Node:
    """Type_Declaration_StmtBase: ``(typespec, attrs?, entities)``."""
    return Node(
        kind=_kind(node),
        edges=_edges(("typespec", "attrs", "entities"), node.items, recurse),
    )


def convert_generic(node: Any, recurse: Recurse) -> Node:
    """Fallback for direct-Base subclasses: positional edge names."""
    items = getattr(node, "items", None)
    if not items:
        s = getattr(node, "string", None)
        if s is not None:
            return Node(kind=_kind(node), value=str(s))
        return Node(kind=_kind(node))

    edges: list[Edge] = []
    for i, item in enumerate(items):
        if item is None:
            continue
        if isinstance(item, Base):
            edges.append(Edge(field_name=f"item_{i}", child=recurse(item)))
        elif isinstance(item, str):
            edges.append(
                Edge(field_name=f"item_{i}", child=Node(kind="token", value=item))
            )
        elif isinstance(item, (list, tuple)):
            for j, sub in enumerate(item):
                child = _item_to_node(sub, recurse)
                if child is not None:
                    edges.append(Edge(field_name=f"item_{i}_{j}", child=child))

    if not edges:
        return Node(kind=_kind(node))
    return Node(kind=_kind(node), edges=tuple(edges))
