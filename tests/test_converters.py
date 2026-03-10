"""Tests for the converter layer: forward, reverse, and round-trip."""

import pytest

import fcst


# ------------------------------------------------------------------
# Fortran test corpus
# ------------------------------------------------------------------

SIMPLE_PROGRAM = """\
PROGRAM hello
  IMPLICIT NONE
  INTEGER :: x
  x = 1
  PRINT *, x
END PROGRAM hello
"""

FUNCTION = """\
FUNCTION add(a, b) RESULT(c)
  IMPLICIT NONE
  INTEGER, INTENT(IN) :: a, b
  INTEGER :: c
  c = a + b
END FUNCTION add
"""

MODULE = """\
MODULE mymod
  IMPLICIT NONE
  INTEGER, PARAMETER :: n = 10
END MODULE mymod
"""

IF_CONSTRUCT = """\
PROGRAM test_if
  IMPLICIT NONE
  INTEGER :: x
  x = 5
  IF (x > 0) THEN
    PRINT *, x
  END IF
END PROGRAM test_if
"""

DO_LOOP = """\
PROGRAM test_do
  IMPLICIT NONE
  INTEGER :: i, s
  s = 0
  DO i = 1, 10
    s = s + i
  END DO
  PRINT *, s
END PROGRAM test_do
"""

SUBROUTINE = """\
SUBROUTINE swap(a, b)
  IMPLICIT NONE
  INTEGER, INTENT(INOUT) :: a, b
  INTEGER :: tmp
  tmp = a
  a = b
  b = tmp
END SUBROUTINE swap
"""

CORPUS = [
    ("simple_program", SIMPLE_PROGRAM),
    ("function", FUNCTION),
    ("module", MODULE),
    ("if_construct", IF_CONSTRUCT),
    ("do_loop", DO_LOOP),
    ("subroutine", SUBROUTINE),
]


# ------------------------------------------------------------------
# Forward converter (str → CST)
# ------------------------------------------------------------------


class TestForwardConverter:
    def test_str_to_cst_returns_node(self):
        cst = fcst.str_to_cst(SIMPLE_PROGRAM)
        assert isinstance(cst, fcst.Node)
        assert cst.kind == "Program"

    def test_program_has_stmts(self):
        cst = fcst.str_to_cst(SIMPLE_PROGRAM)
        # Program is a BlockBase → children are "stmt" edges
        stmts = cst.children("stmt")
        assert len(stmts) > 0

    def test_leaf_values(self):
        cst = fcst.str_to_cst(SIMPLE_PROGRAM)
        # Walk to find a Name node with value "hello"
        found = _find_kind(cst, "Name")
        assert found is not None


# ------------------------------------------------------------------
# Round-trip: str → CST → fparser → str
# ------------------------------------------------------------------


class TestRoundTrip:
    @pytest.mark.parametrize("name,source", CORPUS, ids=[c[0] for c in CORPUS])
    def test_round_trip(self, name, source):
        """cst_to_str(str_to_cst(src)) == ast_to_str(str_to_ast(src))"""
        expected = fcst.ast_to_str(fcst.str_to_ast(source))
        actual = fcst.cst_to_str(fcst.str_to_cst(source))
        assert actual == expected, (
            f"Round-trip mismatch for {name}:\n"
            f"--- expected ---\n{expected}\n"
            f"--- actual ---\n{actual}"
        )


# ------------------------------------------------------------------
# Reverse converter (CST → fparser)
# ------------------------------------------------------------------


class TestReverseConverter:
    def test_cst_to_ast_returns_base(self):
        from fparser.two.utils import Base

        cst = fcst.str_to_cst(SIMPLE_PROGRAM)
        ast = fcst.cst_to_ast(cst)
        assert isinstance(ast, Base)

    def test_unknown_kind_raises(self):
        node = fcst.Node(kind="Nonexistent_Class_XYZ", value="x")
        with pytest.raises(ValueError, match="Unknown fparser class"):
            fcst.cst_to_ast(node)


# ------------------------------------------------------------------
# parse_as (fragment parsing)
# ------------------------------------------------------------------


class TestParseAs:
    def test_use_stmt(self):
        node = fcst.parse_as("use iso_fortran_env", "Use_Stmt")
        assert node.kind == "Use_Stmt"

    def test_assignment_stmt(self):
        node = fcst.parse_as("x = 1", "Assignment_Stmt")
        assert node.kind == "Assignment_Stmt"

    def test_unknown_kind_raises(self):
        with pytest.raises(ValueError, match="Unknown grammar production"):
            fcst.parse_as("x = 1", "Nonexistent_XYZ")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _find_kind(node: fcst.Node, kind: str) -> fcst.Node | None:
    """DFS search for the first node with the given kind."""
    if node.kind == kind:
        return node
    for edge in node.edges:
        result = _find_kind(edge.child, kind)
        if result is not None:
            return result
    return None
