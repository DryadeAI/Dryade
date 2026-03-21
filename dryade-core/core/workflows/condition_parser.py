"""Expression-based condition parser for workflow routers.

Grammar:
  expression := or_expr
  or_expr    := and_expr (OR and_expr)*
  and_expr   := not_expr (AND not_expr)*
  not_expr   := NOT? comparison
  comparison := field_expr (operator value)?
  field_expr := IDENTIFIER ('.' IDENTIFIER | '[' NUMBER ']')*
  operator   := '==' | '!=' | '>' | '<' | '>=' | '<=' | 'contains' | 'matches' | 'in' | 'startswith' | 'endswith'
  value      := STRING | NUMBER | 'null' | 'true' | 'false' | array
  array      := '[' value (',' value)* ']'

Examples:
  status == 'success'
  status == 'success' AND score > 0.8
  error == null OR message contains 'retry'
  result.data.items[0].status == 'complete'
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)

class TokenType(Enum):
    """Token types for lexer."""

    IDENTIFIER = auto()
    STRING = auto()
    NUMBER = auto()
    NULL = auto()
    TRUE = auto()
    FALSE = auto()
    AND = auto()
    OR = auto()
    NOT = auto()
    EQ = auto()  # ==
    NE = auto()  # !=
    GT = auto()  # >
    LT = auto()  # <
    GTE = auto()  # >=
    LTE = auto()  # <=
    CONTAINS = auto()
    MATCHES = auto()
    IN = auto()
    STARTSWITH = auto()
    ENDSWITH = auto()
    DOT = auto()  # .
    LBRACKET = auto()  # [
    RBRACKET = auto()  # ]
    LPAREN = auto()  # (
    RPAREN = auto()  # )
    COMMA = auto()  # ,
    EOF = auto()

@dataclass
class Token:
    """Lexer token."""

    type: TokenType
    value: Any
    pos: int

class ConditionParseError(Exception):
    """Error parsing condition expression."""

    pass

class Lexer:
    """Tokenizer for condition expressions."""

    KEYWORDS = {
        "and": TokenType.AND,
        "or": TokenType.OR,
        "not": TokenType.NOT,
        "null": TokenType.NULL,
        "true": TokenType.TRUE,
        "false": TokenType.FALSE,
        "contains": TokenType.CONTAINS,
        "matches": TokenType.MATCHES,
        "in": TokenType.IN,
        "startswith": TokenType.STARTSWITH,
        "endswith": TokenType.ENDSWITH,
    }

    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.length = len(text)

    def tokenize(self) -> list[Token]:
        """Tokenize the input text."""
        tokens = []

        while self.pos < self.length:
            self._skip_whitespace()
            if self.pos >= self.length:
                break

            char = self.text[self.pos]

            if char == "=" and self._peek(1) == "=":
                tokens.append(Token(TokenType.EQ, "==", self.pos))
                self.pos += 2
            elif char == "!" and self._peek(1) == "=":
                tokens.append(Token(TokenType.NE, "!=", self.pos))
                self.pos += 2
            elif char == ">" and self._peek(1) == "=":
                tokens.append(Token(TokenType.GTE, ">=", self.pos))
                self.pos += 2
            elif char == "<" and self._peek(1) == "=":
                tokens.append(Token(TokenType.LTE, "<=", self.pos))
                self.pos += 2
            elif char == ">":
                tokens.append(Token(TokenType.GT, ">", self.pos))
                self.pos += 1
            elif char == "<":
                tokens.append(Token(TokenType.LT, "<", self.pos))
                self.pos += 1
            elif char == ".":
                tokens.append(Token(TokenType.DOT, ".", self.pos))
                self.pos += 1
            elif char == "[":
                tokens.append(Token(TokenType.LBRACKET, "[", self.pos))
                self.pos += 1
            elif char == "]":
                tokens.append(Token(TokenType.RBRACKET, "]", self.pos))
                self.pos += 1
            elif char == "(":
                tokens.append(Token(TokenType.LPAREN, "(", self.pos))
                self.pos += 1
            elif char == ")":
                tokens.append(Token(TokenType.RPAREN, ")", self.pos))
                self.pos += 1
            elif char == ",":
                tokens.append(Token(TokenType.COMMA, ",", self.pos))
                self.pos += 1
            elif char in ('"', "'"):
                tokens.append(self._read_string(char))
            elif char.isdigit() or (char == "-" and self._peek(1).isdigit()):
                tokens.append(self._read_number())
            elif char.isalpha() or char == "_":
                tokens.append(self._read_identifier())
            else:
                raise ConditionParseError(f"Unexpected character '{char}' at position {self.pos}")

        tokens.append(Token(TokenType.EOF, None, self.pos))
        return tokens

    def _skip_whitespace(self):
        while self.pos < self.length and self.text[self.pos].isspace():
            self.pos += 1

    def _peek(self, offset: int = 0) -> str:
        pos = self.pos + offset
        return self.text[pos] if pos < self.length else ""

    def _read_string(self, quote: str) -> Token:
        start = self.pos
        self.pos += 1  # Skip opening quote
        value = []

        while self.pos < self.length:
            char = self.text[self.pos]
            if char == "\\" and self.pos + 1 < self.length:
                self.pos += 1
                value.append(self.text[self.pos])
            elif char == quote:
                self.pos += 1  # Skip closing quote
                return Token(TokenType.STRING, "".join(value), start)
            else:
                value.append(char)
            self.pos += 1

        raise ConditionParseError(f"Unterminated string starting at position {start}")

    def _read_number(self) -> Token:
        start = self.pos
        value = []

        if self.text[self.pos] == "-":
            value.append("-")
            self.pos += 1

        while self.pos < self.length and (
            self.text[self.pos].isdigit() or self.text[self.pos] == "."
        ):
            value.append(self.text[self.pos])
            self.pos += 1

        num_str = "".join(value)
        num_value = float(num_str) if "." in num_str else int(num_str)
        return Token(TokenType.NUMBER, num_value, start)

    def _read_identifier(self) -> Token:
        start = self.pos
        value = []

        while self.pos < self.length and (
            self.text[self.pos].isalnum() or self.text[self.pos] == "_"
        ):
            value.append(self.text[self.pos])
            self.pos += 1

        ident = "".join(value)
        token_type = self.KEYWORDS.get(ident.lower(), TokenType.IDENTIFIER)
        return Token(token_type, ident, start)

class Parser:
    """Recursive descent parser for condition expressions."""

    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    def parse(self) -> ASTNode:
        """Parse tokens into AST."""
        if self._current().type == TokenType.EOF:
            return LiteralNode(True)  # Empty expression is always true

        result = self._or_expr()

        if self._current().type != TokenType.EOF:
            raise ConditionParseError(f"Unexpected token: {self._current().value}")

        return result

    def _current(self) -> Token:
        return self.tokens[self.pos]

    def _advance(self) -> Token:
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def _expect(self, token_type: TokenType) -> Token:
        token = self._current()
        if token.type != token_type:
            raise ConditionParseError(f"Expected {token_type}, got {token.type}")
        return self._advance()

    def _or_expr(self) -> ASTNode:
        left = self._and_expr()

        while self._current().type == TokenType.OR:
            self._advance()
            right = self._and_expr()
            left = BinaryOpNode("OR", left, right)

        return left

    def _and_expr(self) -> ASTNode:
        left = self._not_expr()

        while self._current().type == TokenType.AND:
            self._advance()
            right = self._not_expr()
            left = BinaryOpNode("AND", left, right)

        return left

    def _not_expr(self) -> ASTNode:
        if self._current().type == TokenType.NOT:
            self._advance()
            return UnaryOpNode("NOT", self._not_expr())

        return self._comparison()

    def _comparison(self) -> ASTNode:
        if self._current().type == TokenType.LPAREN:
            self._advance()
            expr = self._or_expr()
            self._expect(TokenType.RPAREN)
            return expr

        left = self._field_expr()

        op_map = {
            TokenType.EQ: "==",
            TokenType.NE: "!=",
            TokenType.GT: ">",
            TokenType.LT: "<",
            TokenType.GTE: ">=",
            TokenType.LTE: "<=",
            TokenType.CONTAINS: "contains",
            TokenType.MATCHES: "matches",
            TokenType.IN: "in",
            TokenType.STARTSWITH: "startswith",
            TokenType.ENDSWITH: "endswith",
        }

        if self._current().type in op_map:
            op = op_map[self._current().type]
            self._advance()
            right = self._value()
            return ComparisonNode(op, left, right)

        # Single field reference (truthy check)
        return left

    def _field_expr(self) -> ASTNode:
        if self._current().type != TokenType.IDENTIFIER:
            return self._value()

        name = self._advance().value
        path = [name]

        while True:
            if self._current().type == TokenType.DOT:
                self._advance()
                path.append(self._expect(TokenType.IDENTIFIER).value)
            elif self._current().type == TokenType.LBRACKET:
                self._advance()
                index = self._expect(TokenType.NUMBER).value
                self._expect(TokenType.RBRACKET)
                path.append(int(index))
            else:
                break

        return FieldNode(path)

    def _value(self) -> ASTNode:
        token = self._current()

        if token.type == TokenType.STRING or token.type == TokenType.NUMBER:
            self._advance()
            return LiteralNode(token.value)
        elif token.type == TokenType.NULL:
            self._advance()
            return LiteralNode(None)
        elif token.type == TokenType.TRUE:
            self._advance()
            return LiteralNode(True)
        elif token.type == TokenType.FALSE:
            self._advance()
            return LiteralNode(False)
        elif token.type == TokenType.LBRACKET:
            return self._array()
        else:
            raise ConditionParseError(f"Unexpected token: {token.value}")

    def _array(self) -> ASTNode:
        self._expect(TokenType.LBRACKET)
        values = []

        if self._current().type != TokenType.RBRACKET:
            values.append(self._value())
            while self._current().type == TokenType.COMMA:
                self._advance()
                values.append(self._value())

        self._expect(TokenType.RBRACKET)
        return ArrayNode([v.evaluate({}) for v in values])

# AST Nodes

class ASTNode:
    """Base AST node."""

    def evaluate(self, context: dict[str, Any]) -> Any:
        raise NotImplementedError

class LiteralNode(ASTNode):
    """Literal value node."""

    def __init__(self, value: Any):
        self.value = value

    def evaluate(self, context: dict[str, Any]) -> Any:  # noqa: ARG002
        return self.value

class ArrayNode(ASTNode):
    """Array literal node."""

    def __init__(self, values: list[Any]):
        self.values = values

    def evaluate(self, context: dict[str, Any]) -> Any:  # noqa: ARG002
        return self.values

class FieldNode(ASTNode):
    """Field reference node with path."""

    def __init__(self, path: list[str | int]):
        self.path = path

    def evaluate(self, context: dict[str, Any]) -> Any:
        value = context
        for key in self.path:
            if isinstance(key, int):
                if not isinstance(value, (list, tuple)) or key >= len(value):
                    return None
                value = value[key]
            elif isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value

class BinaryOpNode(ASTNode):
    """Binary operation node (AND, OR)."""

    def __init__(self, op: str, left: ASTNode, right: ASTNode):
        self.op = op
        self.left = left
        self.right = right

    def evaluate(self, context: dict[str, Any]) -> Any:
        left_val = self.left.evaluate(context)

        if self.op == "AND":
            if not left_val:
                return False
            return bool(self.right.evaluate(context))
        elif self.op == "OR":
            if left_val:
                return True
            return bool(self.right.evaluate(context))

        raise ConditionParseError(f"Unknown binary operator: {self.op}")

class UnaryOpNode(ASTNode):
    """Unary operation node (NOT)."""

    def __init__(self, op: str, operand: ASTNode):
        self.op = op
        self.operand = operand

    def evaluate(self, context: dict[str, Any]) -> Any:
        if self.op == "NOT":
            return not self.operand.evaluate(context)
        raise ConditionParseError(f"Unknown unary operator: {self.op}")

class ComparisonNode(ASTNode):
    """Comparison operation node."""

    def __init__(self, op: str, left: ASTNode, right: ASTNode):
        self.op = op
        self.left = left
        self.right = right

    def evaluate(self, context: dict[str, Any]) -> Any:
        left_val = self.left.evaluate(context)
        right_val = self.right.evaluate(context)

        if self.op == "==":
            return left_val == right_val
        elif self.op == "!=":
            return left_val != right_val
        elif self.op == ">":
            return self._compare_numeric(left_val, right_val, lambda a, b: a > b)
        elif self.op == "<":
            return self._compare_numeric(left_val, right_val, lambda a, b: a < b)
        elif self.op == ">=":
            return self._compare_numeric(left_val, right_val, lambda a, b: a >= b)
        elif self.op == "<=":
            return self._compare_numeric(left_val, right_val, lambda a, b: a <= b)
        elif self.op == "contains":
            if isinstance(left_val, str) and isinstance(right_val, str):
                return right_val in left_val
            return False
        elif self.op == "matches":
            if isinstance(left_val, str) and isinstance(right_val, str):
                try:
                    return bool(re.search(right_val, left_val))
                except re.error:
                    return False
            return False
        elif self.op == "in":
            if isinstance(right_val, (list, tuple)):
                return left_val in right_val
            return False
        elif self.op == "startswith":
            if isinstance(left_val, str) and isinstance(right_val, str):
                return left_val.startswith(right_val)
            return False
        elif self.op == "endswith":
            if isinstance(left_val, str) and isinstance(right_val, str):
                return left_val.endswith(right_val)
            return False

        raise ConditionParseError(f"Unknown comparison operator: {self.op}")

    def _compare_numeric(self, left: Any, right: Any, comparator) -> bool:
        """Compare with numeric coercion."""
        try:
            if isinstance(left, str):
                left = float(left)
            if isinstance(right, str):
                right = float(right)
            return comparator(left, right)
        except (TypeError, ValueError):
            return False

class ConditionParser:
    """High-level condition parser and evaluator.

    Usage:
        parser = ConditionParser()
        result = parser.evaluate("status == 'success' AND score > 0.8", context)
    """

    def __init__(self):
        self._cache: dict[str, ASTNode] = {}

    def parse(self, expression: str) -> ASTNode:
        """Parse expression to AST (cached)."""
        if expression in self._cache:
            return self._cache[expression]

        lexer = Lexer(expression)
        tokens = lexer.tokenize()
        parser = Parser(tokens)
        ast = parser.parse()

        self._cache[expression] = ast
        return ast

    def evaluate(self, expression: str, context: dict[str, Any]) -> bool:
        """Parse and evaluate expression against context."""
        if not expression or not expression.strip():
            return True  # Empty expression always true

        ast = self.parse(expression.strip())
        return bool(ast.evaluate(context))

# Module-level convenience functions
_parser: ConditionParser | None = None

def parse_condition(expression: str) -> ASTNode:
    """Parse condition expression to AST."""
    global _parser
    if _parser is None:
        _parser = ConditionParser()
    return _parser.parse(expression)

def evaluate_condition(expression: str, context: dict[str, Any]) -> bool:
    """Evaluate condition expression against context."""
    global _parser
    if _parser is None:
        _parser = ConditionParser()
    return _parser.evaluate(expression, context)
