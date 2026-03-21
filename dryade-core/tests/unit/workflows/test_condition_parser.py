"""Comprehensive unit tests for the workflow condition parser.

Tests cover:
- Simple equality/inequality comparisons
- Numeric comparisons (>, <, >=, <=)
- Compound AND/OR expressions
- NOT negation
- Nested field access (dot notation)
- Array index access
- String operators (contains, matches, startswith, endswith)
- 'in' operator with arrays
- Boolean/null comparisons
- Empty/malformed expression edge cases
- Whitespace tolerance
- Parenthesized grouping
- AST caching
- Numeric string coercion
"""

import importlib
import sys
from unittest.mock import MagicMock

import pytest

# The core.workflows.__init__ imports checkpointed_executor which requires crewai.
# Import condition_parser directly to avoid that chain.
_spec = importlib.util.spec_from_file_location(
    "core.workflows.condition_parser",
    str(
        __import__("pathlib").Path(__file__).resolve().parents[3]
        / "core"
        / "workflows"
        / "condition_parser.py"
    ),
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("core.workflows.condition_parser", _mod)
_spec.loader.exec_module(_mod)

ConditionParseError = _mod.ConditionParseError
ConditionParser = _mod.ConditionParser
evaluate_condition = _mod.evaluate_condition
parse_condition = _mod.parse_condition

@pytest.mark.unit
class TestSimpleComparisons:
    """Test simple equality and inequality comparisons."""

    def test_string_equality_true(self):
        assert evaluate_condition("status == 'success'", {"status": "success"}) is True

    def test_string_equality_false(self):
        assert evaluate_condition("status == 'success'", {"status": "failed"}) is False

    def test_string_inequality_true(self):
        assert evaluate_condition("status != 'failed'", {"status": "success"}) is True

    def test_string_inequality_false(self):
        assert evaluate_condition("status != 'success'", {"status": "success"}) is False

    def test_double_quoted_string(self):
        assert evaluate_condition('status == "success"', {"status": "success"}) is True

    def test_integer_equality(self):
        assert evaluate_condition("count == 5", {"count": 5}) is True

    def test_float_equality(self):
        assert evaluate_condition("score == 0.8", {"score": 0.8}) is True

@pytest.mark.unit
class TestNumericComparisons:
    """Test numeric comparison operators."""

    def test_greater_than_true(self):
        assert evaluate_condition("score > 0.8", {"score": 0.9}) is True

    def test_greater_than_false(self):
        assert evaluate_condition("score > 0.8", {"score": 0.5}) is False

    def test_less_than_true(self):
        assert evaluate_condition("count < 10", {"count": 5}) is True

    def test_less_than_false(self):
        assert evaluate_condition("count < 10", {"count": 15}) is False

    def test_greater_equal_true_equal(self):
        assert evaluate_condition("value >= 5", {"value": 5}) is True

    def test_greater_equal_true_greater(self):
        assert evaluate_condition("value >= 5", {"value": 10}) is True

    def test_greater_equal_false(self):
        assert evaluate_condition("value >= 5", {"value": 3}) is False

    def test_less_equal_true_equal(self):
        assert evaluate_condition("value <= 100", {"value": 100}) is True

    def test_less_equal_true_less(self):
        assert evaluate_condition("value <= 100", {"value": 50}) is True

    def test_less_equal_false(self):
        assert evaluate_condition("value <= 100", {"value": 200}) is False

    def test_negative_number(self):
        assert evaluate_condition("temp > -10", {"temp": 5}) is True

    def test_numeric_string_coercion(self):
        """Numeric comparisons should coerce string values."""
        assert evaluate_condition("score > 0.5", {"score": "0.9"}) is True

    def test_incomparable_types_return_false(self):
        """Non-numeric string comparisons should return False, not raise."""
        assert evaluate_condition("name > 5", {"name": "alice"}) is False

@pytest.mark.unit
class TestCompoundConditions:
    """Test AND/OR compound conditions."""

    def test_and_both_true(self):
        ctx = {"status": "success", "score": 0.9}
        assert evaluate_condition("status == 'success' AND score > 0.8", ctx) is True

    def test_and_first_false(self):
        ctx = {"status": "failed", "score": 0.9}
        assert evaluate_condition("status == 'success' AND score > 0.8", ctx) is False

    def test_and_second_false(self):
        ctx = {"status": "success", "score": 0.5}
        assert evaluate_condition("status == 'success' AND score > 0.8", ctx) is False

    def test_or_first_true(self):
        ctx = {"status": "failed", "score": 0.9}
        assert evaluate_condition("status == 'failed' OR score < 0.5", ctx) is True

    def test_or_second_true(self):
        ctx = {"status": "success", "score": 0.3}
        assert evaluate_condition("status == 'failed' OR score < 0.5", ctx) is True

    def test_or_both_false(self):
        ctx = {"status": "success", "score": 0.9}
        assert evaluate_condition("status == 'failed' OR score < 0.5", ctx) is False

    def test_multiple_and(self):
        ctx = {"a": 1, "b": 2, "c": 3}
        assert evaluate_condition("a == 1 AND b == 2 AND c == 3", ctx) is True

    def test_multiple_or(self):
        ctx = {"status": "pending"}
        assert (
            evaluate_condition(
                "status == 'success' OR status == 'pending' OR status == 'retry'", ctx
            )
            is True
        )

    def test_and_or_precedence(self):
        """AND should bind tighter than OR: a OR b AND c == a OR (b AND c)."""
        ctx = {"a": True, "b": False, "c": False}
        # a OR (b AND c) -> True OR False -> True
        assert evaluate_condition("a OR b AND c", ctx) is True

    def test_and_or_precedence_reverse(self):
        """Verify AND-before-OR: a AND b OR c == (a AND b) OR c."""
        ctx = {"a": False, "b": True, "c": True}
        # (a AND b) OR c -> False OR True -> True
        assert evaluate_condition("a AND b OR c", ctx) is True

@pytest.mark.unit
class TestNotOperator:
    """Test NOT unary operator."""

    def test_not_true_becomes_false(self):
        assert evaluate_condition("NOT status == 'failed'", {"status": "success"}) is True

    def test_not_false_becomes_true(self):
        assert evaluate_condition("NOT status == 'success'", {"status": "success"}) is False

    def test_not_with_truthy_field(self):
        assert evaluate_condition("NOT is_active", {"is_active": False}) is True

    def test_double_not(self):
        assert evaluate_condition("NOT NOT is_active", {"is_active": True}) is True

@pytest.mark.unit
class TestNestedFieldAccess:
    """Test dot-notation nested field access."""

    def test_one_level_deep(self):
        ctx = {"result": {"status": "complete"}}
        assert evaluate_condition("result.status == 'complete'", ctx) is True

    def test_two_levels_deep(self):
        ctx = {"result": {"data": {"status": "complete"}}}
        assert evaluate_condition("result.data.status == 'complete'", ctx) is True

    def test_missing_intermediate_field(self):
        """Missing intermediate field should return None, not crash."""
        ctx = {"result": {}}
        assert evaluate_condition("result.data.status == 'complete'", ctx) is False

    def test_non_dict_intermediate(self):
        """Non-dict intermediate should return None, not crash."""
        ctx = {"result": "not_a_dict"}
        assert evaluate_condition("result.data.status == 'complete'", ctx) is False

    def test_missing_top_level_field(self):
        ctx = {}
        assert evaluate_condition("result.status == 'complete'", ctx) is False

@pytest.mark.unit
class TestArrayIndexAccess:
    """Test bracket-notation array index access."""

    def test_simple_array_index(self):
        ctx = {"items": ["a", "b", "c"]}
        assert evaluate_condition("items[0] == 'a'", ctx) is True

    def test_nested_array_field(self):
        ctx = {"items": [{"status": "done"}, {"status": "pending"}]}
        assert evaluate_condition("items[0].status == 'done'", ctx) is True

    def test_out_of_bounds_index(self):
        """Out-of-bounds index should return None, not crash."""
        ctx = {"items": ["a"]}
        assert evaluate_condition("items[5] == 'a'", ctx) is False

    def test_non_list_with_index(self):
        """Index access on non-list should return None."""
        ctx = {"items": "not_a_list"}
        assert evaluate_condition("items[0] == 'a'", ctx) is False

@pytest.mark.unit
class TestStringOperators:
    """Test string-specific operators: contains, matches, startswith, endswith."""

    def test_contains_true(self):
        assert evaluate_condition("message contains 'retry'", {"message": "please retry"}) is True

    def test_contains_false(self):
        assert evaluate_condition("message contains 'error'", {"message": "all good"}) is False

    def test_contains_non_string_left(self):
        assert evaluate_condition("count contains 'x'", {"count": 42}) is False

    def test_startswith_true(self):
        assert evaluate_condition("name startswith 'test'", {"name": "test_workflow"}) is True

    def test_startswith_false(self):
        assert evaluate_condition("name startswith 'prod'", {"name": "test_workflow"}) is False

    def test_endswith_true(self):
        assert evaluate_condition("file endswith '.py'", {"file": "main.py"}) is True

    def test_endswith_false(self):
        assert evaluate_condition("file endswith '.js'", {"file": "main.py"}) is False

    def test_matches_regex(self):
        # Use [0-9] instead of \d since the lexer interprets \ as escape char inside strings
        assert evaluate_condition("code matches '^[0-9]{3}$'", {"code": "200"}) is True

    def test_matches_regex_no_match(self):
        assert evaluate_condition("code matches '^[0-9]{3}$'", {"code": "20"}) is False

    def test_matches_invalid_regex(self):
        """Invalid regex pattern should return False, not raise."""
        assert evaluate_condition("code matches '['", {"code": "test"}) is False

@pytest.mark.unit
class TestInOperator:
    """Test 'in' operator with array literals."""

    def test_in_array_true(self):
        assert evaluate_condition("status in ['success', 'pending']", {"status": "success"}) is True

    def test_in_array_false(self):
        assert evaluate_condition("status in ['success', 'pending']", {"status": "failed"}) is False

    def test_in_numeric_array(self):
        assert evaluate_condition("code in [200, 201, 204]", {"code": 201}) is True

    def test_in_non_array_right(self):
        """'in' with non-array right side should return False."""
        assert evaluate_condition("status in 'success'", {"status": "s"}) is False

@pytest.mark.unit
class TestBooleanAndNullComparisons:
    """Test boolean and null value comparisons."""

    def test_boolean_true_equality(self):
        assert evaluate_condition("is_active == true", {"is_active": True}) is True

    def test_boolean_false_equality(self):
        assert evaluate_condition("is_active == false", {"is_active": False}) is True

    def test_null_equality(self):
        assert evaluate_condition("error == null", {"error": None}) is True

    def test_null_inequality(self):
        assert evaluate_condition("error != null", {"error": "something"}) is True

    def test_truthy_field_check(self):
        """A bare field reference should evaluate as truthy/falsy."""
        assert evaluate_condition("is_active", {"is_active": True}) is True

    def test_falsy_field_check(self):
        assert evaluate_condition("is_active", {"is_active": False}) is False

    def test_none_field_is_falsy(self):
        assert evaluate_condition("value", {"value": None}) is False

@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_expression_returns_true(self):
        assert evaluate_condition("", {}) is True

    def test_whitespace_only_expression_returns_true(self):
        assert evaluate_condition("   ", {}) is True

    def test_extra_whitespace_tolerance(self):
        assert evaluate_condition("  status   ==   'success'  ", {"status": "success"}) is True

    def test_missing_field_is_none(self):
        """Accessing a missing field should give None, not crash."""
        assert evaluate_condition("nonexistent == null", {}) is True

    def test_missing_field_comparison_false(self):
        assert evaluate_condition("nonexistent == 'value'", {}) is False

    def test_malformed_expression_raises(self):
        with pytest.raises(ConditionParseError):
            evaluate_condition("== bad", {})

    def test_unterminated_string_raises(self):
        with pytest.raises(ConditionParseError):
            evaluate_condition("status == 'unterminated", {})

    def test_unexpected_character_raises(self):
        with pytest.raises(ConditionParseError):
            evaluate_condition("status @ 'test'", {})

    def test_parenthesized_expression(self):
        ctx = {"a": True, "b": False, "c": True}
        # (a AND b) OR c -> False OR True -> True
        assert evaluate_condition("(a AND b) OR c", ctx) is True

    def test_parentheses_override_precedence(self):
        ctx = {"a": True, "b": False, "c": True}
        # a AND (b OR c) -> True AND True -> True
        assert evaluate_condition("a AND (b OR c)", ctx) is True

    def test_escaped_quote_in_string(self):
        assert evaluate_condition(r"msg == 'it\'s ok'", {"msg": "it's ok"}) is True

    def test_case_insensitive_keywords(self):
        """AND/OR/NOT should be case-insensitive."""
        ctx = {"a": True, "b": True}
        assert evaluate_condition("a and b", ctx) is True
        assert evaluate_condition("a And b", ctx) is True

@pytest.mark.unit
class TestConditionParserClass:
    """Test the ConditionParser class-level behavior."""

    def test_caching_returns_same_ast(self):
        parser = ConditionParser()
        ast1 = parser.parse("status == 'ok'")
        ast2 = parser.parse("status == 'ok'")
        assert ast1 is ast2

    def test_different_expressions_different_ast(self):
        parser = ConditionParser()
        ast1 = parser.parse("status == 'ok'")
        ast2 = parser.parse("status == 'fail'")
        assert ast1 is not ast2

    def test_module_level_parse_condition(self):
        """Module-level parse_condition convenience function works."""
        ast = parse_condition("status == 'ok'")
        assert ast.evaluate({"status": "ok"}) is True

    def test_module_level_evaluate_condition(self):
        """Module-level evaluate_condition convenience function works."""
        result = evaluate_condition("count > 0", {"count": 5})
        assert result is True
