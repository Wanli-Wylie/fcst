"""Converters targeting the CST representation.

- ast_to_cst : fparser AST  → CST
- str_to_cst : Fortran text  → CST  (composes str_to_ast then ast_to_cst)
"""

from __future__ import annotations

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

from fcst.converters.handlers import (
    convert_binary_op,
    convert_block,
    convert_bracket,
    convert_call,
    convert_end_stmt,
    convert_generic,
    convert_keyword_value,
    convert_number,
    convert_separator,
    convert_sequence,
    convert_string,
    convert_type_decl_stmt,
    convert_unary_op,
    convert_word_cls,
)
from fcst.cst import Node


def ast_to_cst(node: Base) -> Node:
    """Convert an fparser AST node (and all descendants) to a CST Node.

    Dispatch is by structural base class via match-case.  Order matters:
    more specific base classes (EndStmtBase, Type_Declaration_StmtBase)
    must precede their parents (StmtBase → Base) so that the right handler
    is selected for nodes with multiple inheritance.
    """
    match node:
        # --- StmtBase specializations (before generic Base) ---
        case EndStmtBase():
            return convert_end_stmt(node, ast_to_cst)
        case Type_Declaration_StmtBase():
            return convert_type_decl_stmt(node, ast_to_cst)

        # --- Structural base classes ---
        case BlockBase():
            return convert_block(node, ast_to_cst)
        case SequenceBase():
            return convert_sequence(node, ast_to_cst)
        case BinaryOpBase():
            return convert_binary_op(node, ast_to_cst)
        case UnaryOpBase():
            return convert_unary_op(node, ast_to_cst)
        case SeparatorBase():
            return convert_separator(node, ast_to_cst)
        case KeywordValueBase():
            return convert_keyword_value(node, ast_to_cst)
        case BracketBase():
            return convert_bracket(node, ast_to_cst)
        case NumberBase():
            return convert_number(node, ast_to_cst)
        case CallBase():
            return convert_call(node, ast_to_cst)
        case WORDClsBase():
            return convert_word_cls(node, ast_to_cst)

        # --- Leaf tokens ---
        case StringBase():
            return convert_string(node)

        # --- Fallback: direct-Base subclasses with ad-hoc items ---
        case Base():
            return convert_generic(node, ast_to_cst)

        case _:
            raise TypeError(f"Expected fparser Base node, got {type(node)!r}")


def str_to_cst(source: str, std: str = "f2003") -> Node:
    """Parse Fortran source text into a CST Node.

    Composes :func:`~fcst.converters.to_fparser.str_to_ast` and
    :func:`ast_to_cst`.
    """
    from fcst.converters.to_fparser import str_to_ast

    return ast_to_cst(str_to_ast(source, std=std))


def parse_as(text: str, kind: str) -> Node:
    """Parse a text fragment using a specific grammar production.

    *kind* is the fparser class name (e.g. ``'Use_Stmt'``, ``'If_Construct'``).
    The class is resolved via ``getattr(Fortran2003, kind)``; no registry needed.
    """
    from fparser.common.readfortran import FortranStringReader
    from fparser.two import Fortran2003 as f03

    cls = getattr(f03, kind, None)
    if cls is None:
        raise ValueError(f"Unknown grammar production: {kind!r}")
    reader = FortranStringReader(text)
    ast_node = cls(reader)
    if ast_node is None:
        raise ValueError(f"Failed to parse as {kind}: {text!r}")
    return ast_to_cst(ast_node)
