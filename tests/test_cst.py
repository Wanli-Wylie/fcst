"""Tests for the CST node model (Node, Edge, Span)."""

import pytest

from fcst.cst import Edge, Node, Span


class TestSpan:
    def test_length(self):
        s = Span(start=0, end=10)
        assert len(s) == 10

    def test_empty(self):
        s = Span(start=5, end=5)
        assert len(s) == 0

    def test_frozen(self):
        s = Span(start=0, end=10)
        with pytest.raises(Exception):
            s.start = 1


class TestNode:
    def test_leaf(self):
        n = Node(kind="Name", value="x")
        assert n.is_leaf
        assert n.value == "x"
        assert n.edges == ()

    def test_interior(self):
        lhs = Node(kind="Name", value="x")
        rhs = Node(kind="Name", value="y")
        op = Node(kind="token", value="+")
        parent = Node(
            kind="Add_Operand",
            edges=(
                Edge(field_name="lhs", child=lhs),
                Edge(field_name="op", child=op),
                Edge(field_name="rhs", child=rhs),
            ),
        )
        assert not parent.is_leaf
        assert parent.value is None
        assert len(parent.edges) == 3

    def test_leaf_xor_interior(self):
        """Cannot have both value and edges."""
        with pytest.raises(ValueError, match="both value and edges"):
            Node(
                kind="bad",
                value="x",
                edges=(Edge(field_name="a", child=Node(kind="b", value="y")),),
            )

    def test_child_lookup(self):
        c = Node(kind="Name", value="x")
        parent = Node(kind="P", edges=(Edge(field_name="lhs", child=c),))
        assert parent.child("lhs") is c

    def test_child_missing(self):
        parent = Node(kind="P", edges=())
        with pytest.raises(LookupError):
            parent.child("lhs")

    def test_children_container(self):
        stmts = [Node(kind=f"S{i}", value=str(i)) for i in range(3)]
        parent = Node(
            kind="Block",
            edges=tuple(Edge(field_name="stmt", child=s) for s in stmts),
        )
        result = parent.children("stmt")
        assert len(result) == 3
        assert result[0].value == "0"
        assert result[2].value == "2"

    def test_children_empty(self):
        parent = Node(kind="Block", edges=())
        assert parent.children("stmt") == ()


class TestParentLinks:
    def test_root_has_no_parent(self):
        n = Node(kind="Root", value="r")
        assert n.is_root
        assert n.parent is None
        assert n.parent_edge is None

    def test_child_parent(self):
        child = Node(kind="Name", value="x")
        edge = Edge(field_name="lhs", child=child)
        parent = Node(kind="P", edges=(edge,))
        assert child.parent is parent
        assert child.parent_edge is edge
        assert not child.is_root

    def test_deep_parent_chain(self):
        leaf = Node(kind="Leaf", value="v")
        mid = Node(kind="Mid", edges=(Edge(field_name="c", child=leaf),))
        root = Node(kind="Root", edges=(Edge(field_name="c", child=mid),))
        assert leaf.parent is mid
        assert mid.parent is root
        assert root.parent is None
