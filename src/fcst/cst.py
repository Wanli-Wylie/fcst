"""Concrete syntax tree: uniform Node + Edge representation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, PrivateAttr, model_validator


class Span(BaseModel, frozen=True):
    """Half-open byte-offset interval [start, end) in source text."""

    start: int
    end: int

    def __len__(self) -> int:
        return self.end - self.start


class Edge(BaseModel, frozen=True):
    """A labeled, directed link from parent to child.

    For structured nodes: each edge has a unique field_name.
    For container nodes: edges share a field_name and are
    ordered by their position in the edges list.
    """

    field_name: str
    child: Node
    _parent: Node | None = PrivateAttr(default=None)

    def model_post_init(self, __context: Any) -> None:
        self.child._parent = self


class Node(BaseModel, frozen=True):
    """A single node in the concrete syntax tree.

    Leaf (token):    kind is set, value holds the literal text, edges is empty.
    Interior:        kind is set, value is None, edges holds children.
    """

    kind: str
    value: str | None = None
    span: Span | None = None
    edges: tuple[Edge, ...] = ()
    _parent: Edge | None = PrivateAttr(default=None)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def _leaf_xor_interior(self) -> Node:
        if self.value is not None and self.edges:
            raise ValueError(
                f"Node(kind={self.kind!r}) has both value and edges; "
                "a node must be either a leaf (value set) or interior (edges set)"
            )
        return self

    def model_post_init(self, __context: Any) -> None:
        for edge in self.edges:
            edge._parent = self

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    @property
    def parent(self) -> Node | None:
        """The parent Node, or None for the root."""
        if self._parent is None:
            return None
        return self._parent._parent

    @property
    def parent_edge(self) -> Edge | None:
        """The Edge pointing to this node (gives field_name context)."""
        return self._parent

    @property
    def is_leaf(self) -> bool:
        return not self.edges

    @property
    def is_root(self) -> bool:
        return self._parent is None

    def child(self, field_name: str) -> Node:
        """Get the single child for a structured field. Raises on duplicates."""
        found: Node | None = None
        for e in self.edges:
            if e.field_name == field_name:
                if found is not None:
                    raise LookupError(
                        f"Multiple edges named {field_name!r} on {self.kind!r}; "
                        "use children() for container fields"
                    )
                found = e.child
        if found is None:
            raise LookupError(
                f"No edge named {field_name!r} on {self.kind!r}"
            )
        return found

    def children(self, field_name: str) -> tuple[Node, ...]:
        """Get all children for a container field, preserving order."""
        return tuple(e.child for e in self.edges if e.field_name == field_name)


# Pydantic needs the forward-ref resolved after both classes exist.
Edge.model_rebuild()
