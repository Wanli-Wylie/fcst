"""Converters targeting the fparser AST representation.

- str_to_ast : Fortran text  → fparser AST
- cst_to_ast : CST           → fparser AST  (not yet implemented)
"""

from __future__ import annotations

from fparser.common.readfortran import FortranStringReader
from fparser.two.parser import ParserFactory
from fparser.two.utils import Base

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


def cst_to_ast(node: Node) -> Base:
    """Convert a CST Node back to an fparser AST.

    Not yet implemented — requires the schema registry to reconstruct
    the fparser class and its ``items``/``content`` from CST edges.
    """
    raise NotImplementedError(
        "cst_to_ast requires the schema registry (planned for a future session)"
    )
