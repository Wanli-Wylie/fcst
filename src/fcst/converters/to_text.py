"""Converters targeting Fortran source text.

- ast_to_str : fparser AST  → Fortran text
- cst_to_str : CST           → Fortran text  (composes cst_to_ast then ast_to_str)
"""

from __future__ import annotations

from fparser.two.utils import Base

from fcst.cst import Node


def ast_to_str(node: Base) -> str:
    """Reconstruct Fortran source text from an fparser AST node."""
    return node.tofortran()


def cst_to_str(node: Node) -> str:
    """Reconstruct Fortran source text from a CST Node.

    Composes :func:`~fcst.converters.to_fparser.cst_to_ast` and
    :func:`ast_to_str`.
    """
    from fcst.converters.to_fparser import cst_to_ast

    return ast_to_str(cst_to_ast(node))
