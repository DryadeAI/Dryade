"""TDD tests for expression-based condition parser.

Tests the grammar-based expression parsing for workflow router conditions.

RED Phase: Tests written before implementation.
"""

import pytest

class TestComparisonOperators:
    """Test comparison operators: ==, !=, >, <, >=, <="""

    def test_equality_string_match(self):
        """status == 'success' with {"status": "success"} -> True"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("status == 'success'", {"status": "success"})
        assert result is True

    def test_equality_string_no_match(self):
        """status == 'success' with {"status": "failed"} -> False"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("status == 'success'", {"status": "failed"})
        assert result is False

    def test_equality_null(self):
        """error == null with {"error": null} -> True"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("error == null", {"error": None})
        assert result is True

    def test_equality_number(self):
        """score == 0.9 with {"score": 0.9} -> True"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("score == 0.9", {"score": 0.9})
        assert result is True

    def test_inequality_string(self):
        """status != 'failed' with {"status": "success"} -> True"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("status != 'failed'", {"status": "success"})
        assert result is True

    def test_greater_than_true(self):
        """score > 0.8 with {"score": 0.9} -> True"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("score > 0.8", {"score": 0.9})
        assert result is True

    def test_greater_than_false(self):
        """score > 0.8 with {"score": 0.7} -> False"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("score > 0.8", {"score": 0.7})
        assert result is False

    def test_less_than(self):
        """count < 10 with {"count": 5} -> True"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("count < 10", {"count": 5})
        assert result is True

    def test_greater_than_or_equal(self):
        """score >= 0.8 with {"score": 0.8} -> True"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("score >= 0.8", {"score": 0.8})
        assert result is True

    def test_less_than_or_equal(self):
        """count <= 10 with {"count": 10} -> True"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("count <= 10", {"count": 10})
        assert result is True

class TestStringOperators:
    """Test string operators: contains, matches, startswith, endswith"""

    def test_contains_true(self):
        """message contains 'error' with {"message": "An error occurred"} -> True"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("message contains 'error'", {"message": "An error occurred"})
        assert result is True

    def test_contains_false(self):
        """message contains 'error' with {"message": "Success!"} -> False"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("message contains 'error'", {"message": "Success!"})
        assert result is False

    def test_matches_regex_true(self):
        """code matches '^ERR_.*' with {"code": "ERR_TIMEOUT"} -> True"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("code matches '^ERR_.*'", {"code": "ERR_TIMEOUT"})
        assert result is True

    def test_matches_regex_false(self):
        """code matches '^ERR_.*' with {"code": "SUCCESS"} -> False"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("code matches '^ERR_.*'", {"code": "SUCCESS"})
        assert result is False

    def test_startswith_true(self):
        """name startswith 'test_' with {"name": "test_function"} -> True"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("name startswith 'test_'", {"name": "test_function"})
        assert result is True

    def test_startswith_false(self):
        """name startswith 'test_' with {"name": "main_function"} -> False"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("name startswith 'test_'", {"name": "main_function"})
        assert result is False

    def test_endswith_true(self):
        """file endswith '.py' with {"file": "script.py"} -> True"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("file endswith '.py'", {"file": "script.py"})
        assert result is True

    def test_endswith_false(self):
        """file endswith '.py' with {"file": "script.js"} -> False"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("file endswith '.py'", {"file": "script.js"})
        assert result is False

class TestCollectionOperator:
    """Test collection operator: in"""

    def test_in_array_true(self):
        """type in ['high', 'critical'] with {"type": "high"} -> True"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("type in ['high', 'critical']", {"type": "high"})
        assert result is True

    def test_in_array_false(self):
        """type in ['high', 'critical'] with {"type": "low"} -> False"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("type in ['high', 'critical']", {"type": "low"})
        assert result is False

    def test_in_with_numbers(self):
        """priority in [1, 2, 3] with {"priority": 2} -> True"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("priority in [1, 2, 3]", {"priority": 2})
        assert result is True

class TestBooleanLogic:
    """Test boolean logic: AND, OR, NOT with proper precedence"""

    def test_and_both_true(self):
        """status == 'success' AND score > 0.8 with matching context -> True"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition(
            "status == 'success' AND score > 0.8", {"status": "success", "score": 0.9}
        )
        assert result is True

    def test_and_one_false(self):
        """status == 'success' AND score > 0.8 with low score -> False"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition(
            "status == 'success' AND score > 0.8", {"status": "success", "score": 0.7}
        )
        assert result is False

    def test_or_first_true(self):
        """status == 'success' OR status == 'partial' with success -> True"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition(
            "status == 'success' OR status == 'partial'", {"status": "success"}
        )
        assert result is True

    def test_or_second_true(self):
        """status == 'success' OR status == 'partial' with partial -> True"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition(
            "status == 'success' OR status == 'partial'", {"status": "partial"}
        )
        assert result is True

    def test_or_both_false(self):
        """status == 'success' OR status == 'partial' with failed -> False"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition(
            "status == 'success' OR status == 'partial'", {"status": "failed"}
        )
        assert result is False

    def test_not_with_null(self):
        """NOT error with {"error": null} -> True"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("NOT error", {"error": None})
        assert result is True

    def test_not_with_value(self):
        """NOT error with {"error": "something"} -> False"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("NOT error", {"error": "something"})
        assert result is False

    def test_operator_precedence_and_or(self):
        """AND has higher precedence than OR"""
        from core.workflows.condition_parser import evaluate_condition

        # a OR b AND c should be a OR (b AND c)
        # If a=True, b=False, c=False: result should be True (because a is True)
        result = evaluate_condition("a == 1 OR b == 1 AND c == 1", {"a": 1, "b": 0, "c": 0})
        assert result is True

        # If a=False, b=True, c=True: result should be True (because b AND c is True)
        result = evaluate_condition("a == 1 OR b == 1 AND c == 1", {"a": 0, "b": 1, "c": 1})
        assert result is True

        # If a=False, b=True, c=False: result should be False
        result = evaluate_condition("a == 1 OR b == 1 AND c == 1", {"a": 0, "b": 1, "c": 0})
        assert result is False

class TestFieldAccess:
    """Test nested field access and array indexing"""

    def test_nested_field_access(self):
        """result.data.value == 42 with nested dict -> True"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("result.data.value == 42", {"result": {"data": {"value": 42}}})
        assert result is True

    def test_nested_field_access_missing(self):
        """result.data.value == 42 with missing intermediate -> False"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("result.data.value == 42", {"result": {"other": 1}})
        assert result is False

    def test_array_index_access(self):
        """items[0].name == 'first' with array -> True"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition(
            "items[0].name == 'first'", {"items": [{"name": "first"}, {"name": "second"}]}
        )
        assert result is True

    def test_array_index_out_of_bounds(self):
        """items[5].name == 'test' with small array -> False"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("items[5].name == 'test'", {"items": [{"name": "first"}]})
        assert result is False

class TestTypeCoercion:
    """Test type coercion for numeric comparisons"""

    def test_string_to_number_comparison(self):
        """count > 5 with {"count": "10"} -> True (coerces string to number)"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("count > 5", {"count": "10"})
        assert result is True

    def test_numeric_comparison_with_int_and_float(self):
        """score >= 5 with {"score": 5.0} -> True"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("score >= 5", {"score": 5.0})
        assert result is True

class TestEdgeCases:
    """Test edge cases: empty expression, invalid expression, special values"""

    def test_empty_expression_returns_true(self):
        """Empty condition '' -> True (always passes)"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("", {"any": "context"})
        assert result is True

    def test_whitespace_only_returns_true(self):
        """Whitespace-only condition '   ' -> True"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("   ", {"any": "context"})
        assert result is True

    def test_invalid_expression_raises_error(self):
        """Invalid expression raises ConditionParseError"""
        from core.workflows.condition_parser import (
            ConditionParseError,
            evaluate_condition,
        )

        with pytest.raises(ConditionParseError):
            evaluate_condition("status == == 'bad'", {"status": "test"})

    def test_unterminated_string_raises_error(self):
        """Unterminated string raises ConditionParseError"""
        from core.workflows.condition_parser import (
            ConditionParseError,
            evaluate_condition,
        )

        with pytest.raises(ConditionParseError):
            evaluate_condition("status == 'unterminated", {"status": "test"})

    def test_boolean_true_literal(self):
        """active == true with {"active": true} -> True"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("active == true", {"active": True})
        assert result is True

    def test_boolean_false_literal(self):
        """disabled == false with {"disabled": false} -> True"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("disabled == false", {"disabled": False})
        assert result is True

    def test_double_quoted_string(self):
        """status == "success" (double quotes) with {"status": "success"} -> True"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition('status == "success"', {"status": "success"})
        assert result is True

class TestPublicAPI:
    """Test public API exports"""

    def test_evaluate_condition_function(self):
        """evaluate_condition module-level function works"""
        from core.workflows.condition_parser import evaluate_condition

        result = evaluate_condition("x == 1", {"x": 1})
        assert result is True

    def test_parse_condition_function(self):
        """parse_condition returns AST node"""
        from core.workflows.condition_parser import parse_condition

        ast = parse_condition("x == 1")
        assert ast is not None

    def test_condition_parser_class(self):
        """ConditionParser class works with caching"""
        from core.workflows.condition_parser import ConditionParser

        parser = ConditionParser()
        result1 = parser.evaluate("status == 'ok'", {"status": "ok"})
        result2 = parser.evaluate("status == 'ok'", {"status": "ok"})
        assert result1 is True
        assert result2 is True

class TestLexer:
    """Test lexer tokenization"""

    def test_tokenize_comparison(self):
        """Lexer tokenizes comparison expression correctly"""
        from core.workflows.condition_parser import Lexer, TokenType

        lexer = Lexer("status == 'success'")
        tokens = lexer.tokenize()

        assert tokens[0].type == TokenType.IDENTIFIER
        assert tokens[0].value == "status"
        assert tokens[1].type == TokenType.EQ
        assert tokens[2].type == TokenType.STRING
        assert tokens[2].value == "success"
        assert tokens[3].type == TokenType.EOF

    def test_tokenize_negative_number(self):
        """Lexer handles negative numbers"""
        from core.workflows.condition_parser import Lexer, TokenType

        lexer = Lexer("value > -10")
        tokens = lexer.tokenize()

        assert tokens[2].type == TokenType.NUMBER
        assert tokens[2].value == -10

    def test_tokenize_float(self):
        """Lexer handles floating point numbers"""
        from core.workflows.condition_parser import Lexer, TokenType

        lexer = Lexer("score >= 0.85")
        tokens = lexer.tokenize()

        assert tokens[2].type == TokenType.NUMBER
        assert tokens[2].value == 0.85

class TestParentheses:
    """Test parentheses for grouping"""

    def test_parentheses_override_precedence(self):
        """(a OR b) AND c - parentheses override AND precedence"""
        from core.workflows.condition_parser import evaluate_condition

        # Without parens: a OR (b AND c) - a=False, b=True, c=False => False
        # With parens: (a OR b) AND c - a=False, b=True, c=False => (True) AND False => False
        result = evaluate_condition("(a == 1 OR b == 1) AND c == 1", {"a": 0, "b": 1, "c": 0})
        assert result is False

        # (a OR b) AND c where a=True, b=False, c=True => (True) AND True => True
        result = evaluate_condition("(a == 1 OR b == 1) AND c == 1", {"a": 1, "b": 0, "c": 1})
        assert result is True
