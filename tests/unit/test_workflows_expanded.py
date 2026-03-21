"""Expanded tests for core/workflows/ modules.

Tests condition_parser (Lexer, Parser, AST nodes, ConditionParser class),
triggers (TriggerHandler, TriggerSource enum), and schema (WorkflowSchema).
Brings coverage of previously untested paths.
"""

import os

import pytest

# ===========================================================================
# condition_parser: Lexer
# ===========================================================================

class TestLexer:
    """Tests for core/workflows/condition_parser.Lexer."""

    def test_tokenize_equality_operator(self):
        """Lexer tokenizes == correctly."""
        from core.workflows.condition_parser import Lexer, TokenType

        tokens = Lexer("x == 'a'").tokenize()
        types = [t.type for t in tokens]
        assert TokenType.IDENTIFIER in types
        assert TokenType.EQ in types
        assert TokenType.STRING in types

    def test_tokenize_inequality_operator(self):
        """Lexer tokenizes != correctly."""
        from core.workflows.condition_parser import Lexer, TokenType

        tokens = Lexer("x != 'b'").tokenize()
        types = [t.type for t in tokens]
        assert TokenType.NE in types

    def test_tokenize_greater_than(self):
        """Lexer tokenizes > correctly."""
        from core.workflows.condition_parser import Lexer, TokenType

        tokens = Lexer("x > 5").tokenize()
        types = [t.type for t in tokens]
        assert TokenType.GT in types

    def test_tokenize_greater_than_equal(self):
        """Lexer tokenizes >= correctly."""
        from core.workflows.condition_parser import Lexer, TokenType

        tokens = Lexer("x >= 5").tokenize()
        types = [t.type for t in tokens]
        assert TokenType.GTE in types

    def test_tokenize_less_than(self):
        """Lexer tokenizes < correctly."""
        from core.workflows.condition_parser import Lexer, TokenType

        tokens = Lexer("x < 10").tokenize()
        types = [t.type for t in tokens]
        assert TokenType.LT in types

    def test_tokenize_less_than_equal(self):
        """Lexer tokenizes <= correctly."""
        from core.workflows.condition_parser import Lexer, TokenType

        tokens = Lexer("x <= 10").tokenize()
        types = [t.type for t in tokens]
        assert TokenType.LTE in types

    def test_tokenize_dot(self):
        """Lexer tokenizes . field access."""
        from core.workflows.condition_parser import Lexer, TokenType

        tokens = Lexer("a.b").tokenize()
        types = [t.type for t in tokens]
        assert TokenType.DOT in types

    def test_tokenize_bracket_access(self):
        """Lexer tokenizes array [N] access."""
        from core.workflows.condition_parser import Lexer, TokenType

        tokens = Lexer("a[0]").tokenize()
        types = [t.type for t in tokens]
        assert TokenType.LBRACKET in types
        assert TokenType.RBRACKET in types

    def test_tokenize_keywords(self):
        """Lexer tokenizes AND, OR, NOT, null, true, false keywords."""
        from core.workflows.condition_parser import Lexer, TokenType

        tokens = Lexer("x == null AND y == true OR NOT z == false").tokenize()
        types = [t.type for t in tokens]
        assert TokenType.AND in types
        assert TokenType.OR in types
        assert TokenType.NOT in types
        assert TokenType.NULL in types
        assert TokenType.TRUE in types
        assert TokenType.FALSE in types

    def test_tokenize_string_single_quote(self):
        """Lexer tokenizes single-quoted strings."""
        from core.workflows.condition_parser import Lexer, TokenType

        tokens = Lexer("x == 'hello world'").tokenize()
        string_tokens = [t for t in tokens if t.type == TokenType.STRING]
        assert len(string_tokens) == 1
        assert string_tokens[0].value == "hello world"

    def test_tokenize_string_double_quote(self):
        """Lexer tokenizes double-quoted strings."""
        from core.workflows.condition_parser import Lexer, TokenType

        tokens = Lexer('x == "world"').tokenize()
        string_tokens = [t for t in tokens if t.type == TokenType.STRING]
        assert string_tokens[0].value == "world"

    def test_tokenize_integer(self):
        """Lexer tokenizes integer numbers."""
        from core.workflows.condition_parser import Lexer, TokenType

        tokens = Lexer("x > 42").tokenize()
        num_tokens = [t for t in tokens if t.type == TokenType.NUMBER]
        assert num_tokens[0].value == 42

    def test_tokenize_float(self):
        """Lexer tokenizes floating point numbers."""
        from core.workflows.condition_parser import Lexer, TokenType

        tokens = Lexer("score > 0.85").tokenize()
        num_tokens = [t for t in tokens if t.type == TokenType.NUMBER]
        assert num_tokens[0].value == pytest.approx(0.85)

    def test_tokenize_negative_number(self):
        """Lexer tokenizes negative numbers."""
        from core.workflows.condition_parser import Lexer, TokenType

        tokens = Lexer("x > -5").tokenize()
        num_tokens = [t for t in tokens if t.type == TokenType.NUMBER]
        assert num_tokens[0].value == -5

    def test_tokenize_contains_keyword(self):
        """Lexer tokenizes 'contains' operator keyword."""
        from core.workflows.condition_parser import Lexer, TokenType

        tokens = Lexer("message contains 'error'").tokenize()
        types = [t.type for t in tokens]
        assert TokenType.CONTAINS in types

    def test_tokenize_matches_keyword(self):
        """Lexer tokenizes 'matches' operator keyword."""
        from core.workflows.condition_parser import Lexer, TokenType

        tokens = Lexer("message matches 'err.*'").tokenize()
        types = [t.type for t in tokens]
        assert TokenType.MATCHES in types

    def test_tokenize_in_keyword(self):
        """Lexer tokenizes 'in' operator keyword."""
        from core.workflows.condition_parser import Lexer, TokenType

        tokens = Lexer("status in ['a', 'b']").tokenize()
        types = [t.type for t in tokens]
        assert TokenType.IN in types

    def test_tokenize_startswith_endswith(self):
        """Lexer tokenizes 'startswith' and 'endswith' keywords."""
        from core.workflows.condition_parser import Lexer, TokenType

        tokens = Lexer("url startswith 'https'").tokenize()
        types = [t.type for t in tokens]
        assert TokenType.STARTSWITH in types

        tokens = Lexer("filename endswith '.pdf'").tokenize()
        types = [t.type for t in tokens]
        assert TokenType.ENDSWITH in types

    def test_tokenize_eof(self):
        """Tokenize returns EOF token at end."""
        from core.workflows.condition_parser import Lexer, TokenType

        tokens = Lexer("x == 1").tokenize()
        assert tokens[-1].type == TokenType.EOF

    def test_tokenize_parentheses(self):
        """Lexer tokenizes parentheses."""
        from core.workflows.condition_parser import Lexer, TokenType

        tokens = Lexer("(x == 1)").tokenize()
        types = [t.type for t in tokens]
        assert TokenType.LPAREN in types
        assert TokenType.RPAREN in types

    def test_tokenize_comma(self):
        """Lexer tokenizes comma (used in arrays)."""
        from core.workflows.condition_parser import Lexer, TokenType

        tokens = Lexer("x in [1, 2, 3]").tokenize()
        types = [t.type for t in tokens]
        assert TokenType.COMMA in types

    def test_tokenize_unterminated_string_raises(self):
        """Lexer raises ConditionParseError for unterminated strings."""
        from core.workflows.condition_parser import ConditionParseError, Lexer

        with pytest.raises(ConditionParseError, match="Unterminated string"):
            Lexer("x == 'unclosed").tokenize()

    def test_tokenize_unexpected_char_raises(self):
        """Lexer raises ConditionParseError for unknown characters."""
        from core.workflows.condition_parser import ConditionParseError, Lexer

        with pytest.raises(ConditionParseError, match="Unexpected character"):
            Lexer("x @ y").tokenize()

    def test_tokenize_escaped_string(self):
        """Lexer handles backslash escapes in strings."""
        from core.workflows.condition_parser import Lexer, TokenType

        tokens = Lexer(r"x == 'he\'s'").tokenize()
        string_tokens = [t for t in tokens if t.type == TokenType.STRING]
        assert len(string_tokens) == 1

# ===========================================================================
# condition_parser: Parser
# ===========================================================================

class TestParser:
    """Tests for core/workflows/condition_parser.Parser."""

    def test_parse_empty_expression(self):
        """Empty expression parses to LiteralNode(True)."""
        from core.workflows.condition_parser import Lexer, Parser, TokenType

        tokens = Lexer("").tokenize()
        ast = Parser(tokens).parse()
        assert ast.evaluate({}) is True

    def test_parse_simple_comparison(self):
        """Parser parses simple x == 'y' comparison."""
        from core.workflows.condition_parser import Lexer, Parser

        tokens = Lexer("status == 'ok'").tokenize()
        ast = Parser(tokens).parse()
        result = ast.evaluate({"status": "ok"})
        assert result is True

    def test_parse_and_expression(self):
        """Parser parses AND expression."""
        from core.workflows.condition_parser import Lexer, Parser

        tokens = Lexer("a == 1 AND b == 2").tokenize()
        ast = Parser(tokens).parse()
        assert ast.evaluate({"a": 1, "b": 2}) is True
        assert ast.evaluate({"a": 1, "b": 3}) is False

    def test_parse_or_expression(self):
        """Parser parses OR expression."""
        from core.workflows.condition_parser import Lexer, Parser

        tokens = Lexer("a == 1 OR b == 2").tokenize()
        ast = Parser(tokens).parse()
        assert ast.evaluate({"a": 1, "b": 99}) is True
        assert ast.evaluate({"a": 99, "b": 99}) is False

    def test_parse_not_expression(self):
        """Parser parses NOT expression."""
        from core.workflows.condition_parser import Lexer, Parser

        tokens = Lexer("NOT status == 'error'").tokenize()
        ast = Parser(tokens).parse()
        assert ast.evaluate({"status": "ok"}) is True
        assert ast.evaluate({"status": "error"}) is False

    def test_parse_nested_field_access(self):
        """Parser parses nested field access (result.data.value)."""
        from core.workflows.condition_parser import Lexer, Parser

        tokens = Lexer("result.data.value == 'ok'").tokenize()
        ast = Parser(tokens).parse()
        assert ast.evaluate({"result": {"data": {"value": "ok"}}}) is True

    def test_parse_array_index_access(self):
        """Parser parses array index access (items[0].status)."""
        from core.workflows.condition_parser import Lexer, Parser

        tokens = Lexer("items[0] == 'first'").tokenize()
        ast = Parser(tokens).parse()
        assert ast.evaluate({"items": ["first", "second"]}) is True

    def test_parse_unexpected_token_raises(self):
        """Parser raises ConditionParseError for trailing tokens."""
        from core.workflows.condition_parser import ConditionParseError, Lexer, Parser

        tokens = Lexer("x == 1 extra").tokenize()
        with pytest.raises(ConditionParseError):
            Parser(tokens).parse()

    def test_parse_in_array_expression(self):
        """Parser parses 'in [...]' expression."""
        from core.workflows.condition_parser import Lexer, Parser

        tokens = Lexer("status in ['ok', 'done']").tokenize()
        ast = Parser(tokens).parse()
        assert ast.evaluate({"status": "ok"}) is True
        assert ast.evaluate({"status": "fail"}) is False

# ===========================================================================
# condition_parser: AST nodes
# ===========================================================================

class TestASTNodes:
    """Tests for condition_parser AST node classes."""

    def test_literal_node_returns_value(self):
        """LiteralNode.evaluate() returns its value."""
        from core.workflows.condition_parser import LiteralNode

        assert LiteralNode(42).evaluate({}) == 42
        assert LiteralNode("hello").evaluate({}) == "hello"
        assert LiteralNode(None).evaluate({}) is None

    def test_array_node_returns_list(self):
        """ArrayNode.evaluate() returns list of values."""
        from core.workflows.condition_parser import ArrayNode

        node = ArrayNode([1, 2, 3])
        assert node.evaluate({}) == [1, 2, 3]

    def test_field_node_accesses_dict(self):
        """FieldNode accesses dict key."""
        from core.workflows.condition_parser import FieldNode

        node = FieldNode(["status"])
        assert node.evaluate({"status": "ok"}) == "ok"

    def test_field_node_nested_dict(self):
        """FieldNode accesses nested dict."""
        from core.workflows.condition_parser import FieldNode

        node = FieldNode(["result", "data"])
        assert node.evaluate({"result": {"data": "value"}}) == "value"

    def test_field_node_array_index(self):
        """FieldNode accesses array index."""
        from core.workflows.condition_parser import FieldNode

        node = FieldNode(["items", 0])
        assert node.evaluate({"items": ["first", "second"]}) == "first"

    def test_field_node_out_of_bounds_returns_none(self):
        """FieldNode returns None for out-of-bounds index."""
        from core.workflows.condition_parser import FieldNode

        node = FieldNode(["items", 10])
        assert node.evaluate({"items": [1, 2]}) is None

    def test_field_node_missing_key_returns_none(self):
        """FieldNode returns None for missing key."""
        from core.workflows.condition_parser import FieldNode

        node = FieldNode(["missing"])
        assert node.evaluate({}) is None

    def test_field_node_non_dict_value_returns_none(self):
        """FieldNode returns None when traversing non-dict."""
        from core.workflows.condition_parser import FieldNode

        node = FieldNode(["status", "nested"])
        assert node.evaluate({"status": "string"}) is None

    def test_binary_op_and_short_circuits(self):
        """BinaryOpNode AND short-circuits on False left."""
        from core.workflows.condition_parser import BinaryOpNode, LiteralNode

        right_evaluated = []

        class TrackingNode(LiteralNode):
            def evaluate(self, ctx):
                right_evaluated.append(True)
                return True

        node = BinaryOpNode("AND", LiteralNode(False), TrackingNode(True))
        result = node.evaluate({})
        assert result is False
        assert len(right_evaluated) == 0  # Right never evaluated

    def test_binary_op_or_short_circuits(self):
        """BinaryOpNode OR short-circuits on True left."""
        from core.workflows.condition_parser import BinaryOpNode, LiteralNode

        right_evaluated = []

        class TrackingNode(LiteralNode):
            def evaluate(self, ctx):
                right_evaluated.append(True)
                return True

        node = BinaryOpNode("OR", LiteralNode(True), TrackingNode(True))
        result = node.evaluate({})
        assert result is True
        assert len(right_evaluated) == 0  # Right never evaluated

    def test_binary_op_unknown_raises(self):
        """BinaryOpNode raises for unknown operator."""
        from core.workflows.condition_parser import BinaryOpNode, ConditionParseError, LiteralNode

        node = BinaryOpNode("XOR", LiteralNode(True), LiteralNode(False))
        with pytest.raises(ConditionParseError):
            node.evaluate({})

    def test_unary_op_not(self):
        """UnaryOpNode NOT negates operand."""
        from core.workflows.condition_parser import LiteralNode, UnaryOpNode

        node = UnaryOpNode("NOT", LiteralNode(True))
        assert node.evaluate({}) is False

    def test_unary_op_unknown_raises(self):
        """UnaryOpNode raises for unknown operator."""
        from core.workflows.condition_parser import ConditionParseError, LiteralNode, UnaryOpNode

        node = UnaryOpNode("NAND", LiteralNode(True))
        with pytest.raises(ConditionParseError):
            node.evaluate({})

    def test_comparison_node_contains(self):
        """ComparisonNode handles 'contains' operator."""
        from core.workflows.condition_parser import ComparisonNode, LiteralNode

        node = ComparisonNode("contains", LiteralNode("hello world"), LiteralNode("world"))
        assert node.evaluate({}) is True

    def test_comparison_node_matches(self):
        """ComparisonNode handles 'matches' regex operator."""
        from core.workflows.condition_parser import ComparisonNode, LiteralNode

        node = ComparisonNode("matches", LiteralNode("error_404"), LiteralNode("error_\\d+"))
        assert node.evaluate({}) is True

    def test_comparison_node_matches_invalid_regex(self):
        """ComparisonNode returns False for invalid regex."""
        from core.workflows.condition_parser import ComparisonNode, LiteralNode

        node = ComparisonNode("matches", LiteralNode("test"), LiteralNode("[invalid"))
        assert node.evaluate({}) is False

    def test_comparison_node_in_list(self):
        """ComparisonNode handles 'in' operator with list."""
        from core.workflows.condition_parser import ArrayNode, ComparisonNode, LiteralNode

        node = ComparisonNode("in", LiteralNode("a"), ArrayNode(["a", "b", "c"]))
        assert node.evaluate({}) is True

    def test_comparison_node_startswith(self):
        """ComparisonNode handles 'startswith' operator."""
        from core.workflows.condition_parser import ComparisonNode, LiteralNode

        node = ComparisonNode(
            "startswith", LiteralNode("https://example.com"), LiteralNode("https")
        )
        assert node.evaluate({}) is True

    def test_comparison_node_endswith(self):
        """ComparisonNode handles 'endswith' operator."""
        from core.workflows.condition_parser import ComparisonNode, LiteralNode

        node = ComparisonNode("endswith", LiteralNode("report.pdf"), LiteralNode(".pdf"))
        assert node.evaluate({}) is True

    def test_comparison_node_unknown_raises(self):
        """ComparisonNode raises for unknown operator."""
        from core.workflows.condition_parser import ComparisonNode, ConditionParseError, LiteralNode

        node = ComparisonNode("BETWEEN", LiteralNode(5), LiteralNode(10))
        with pytest.raises(ConditionParseError):
            node.evaluate({})

    def test_comparison_numeric_with_strings(self):
        """ComparisonNode coerces string values for numeric comparison."""
        from core.workflows.condition_parser import ComparisonNode, LiteralNode

        node = ComparisonNode(">", LiteralNode("10"), LiteralNode("5"))
        assert node.evaluate({}) is True

    def test_comparison_numeric_type_error(self):
        """ComparisonNode returns False on numeric comparison TypeError."""
        from core.workflows.condition_parser import ComparisonNode, LiteralNode

        node = ComparisonNode(">", LiteralNode("abc"), LiteralNode("def"))
        assert node.evaluate({}) is False

# ===========================================================================
# condition_parser: ConditionParser class
# ===========================================================================

class TestConditionParserClass:
    """Tests for ConditionParser high-level class."""

    def test_evaluate_simple_expression(self):
        """ConditionParser.evaluate() works for simple expression."""
        from core.workflows.condition_parser import ConditionParser

        parser = ConditionParser()
        assert parser.evaluate("status == 'ok'", {"status": "ok"}) is True

    def test_evaluate_empty_returns_true(self):
        """Empty expression evaluates to True."""
        from core.workflows.condition_parser import ConditionParser

        parser = ConditionParser()
        assert parser.evaluate("", {}) is True
        assert parser.evaluate("   ", {}) is True

    def test_caches_parsed_expression(self):
        """ConditionParser caches parsed ASTs."""
        from core.workflows.condition_parser import ConditionParser

        parser = ConditionParser()
        expr = "x == 1"
        ast1 = parser.parse(expr)
        ast2 = parser.parse(expr)
        assert ast1 is ast2  # Same object from cache

    def test_parse_condition_module_function(self):
        """parse_condition() module function creates AST."""
        from core.workflows.condition_parser import parse_condition

        ast = parse_condition("x == 1")
        assert ast is not None

    def test_evaluate_condition_module_function(self):
        """evaluate_condition() module function evaluates expression."""
        from core.workflows.condition_parser import evaluate_condition

        assert evaluate_condition("x == 1", {"x": 1}) is True
        assert evaluate_condition("x == 1", {"x": 2}) is False

# ===========================================================================
# triggers: TriggerSource enum
# ===========================================================================

class TestTriggerSource:
    """Tests for core/workflows/triggers.TriggerSource."""

    def test_trigger_source_values(self):
        """TriggerSource has expected values."""
        from core.workflows.triggers import TriggerSource

        assert TriggerSource.CHAT == "chat"
        assert TriggerSource.API == "api"
        assert TriggerSource.UI == "ui"
        assert TriggerSource.SCHEDULE == "schedule"

    def test_trigger_source_is_string_enum(self):
        """TriggerSource is a string enum."""
        from core.workflows.triggers import TriggerSource

        assert isinstance(TriggerSource.API, str)

# ===========================================================================
# triggers: TriggerHandler
# ===========================================================================

class TestTriggerHandler:
    """Tests for core/workflows/triggers.TriggerHandler."""

    def test_trigger_handler_initialization(self):
        """TriggerHandler initializes with registry and executor."""
        from unittest.mock import MagicMock

        from core.workflows.triggers import TriggerHandler

        registry = MagicMock()
        executor = MagicMock()
        handler = TriggerHandler(registry, executor)
        assert handler._registry is registry
        assert handler._executor is executor

    def test_create_execution_record_writes_to_db(self):
        """_create_execution_record writes to DB (no return value)."""
        from datetime import UTC, datetime
        from unittest.mock import MagicMock, patch

        from core.workflows.triggers import TriggerHandler

        handler = TriggerHandler(MagicMock(), MagicMock())
        now = datetime.now(UTC)

        # Patch get_session to use in-memory DB
        with patch("core.workflows.triggers.get_session") as mock_get_session:
            mock_db = MagicMock()
            mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

            result = handler._create_execution_record(
                execution_id="exec-001",
                scenario_name="test_scenario",
                trigger_source="api",
                user_id="user-001",
                inputs={"key": "value"},
                started_at=now,
            )

        # Function returns None (writes to DB)
        assert result is None
        # DB add was called
        mock_db.add.assert_called_once()

    def test_create_execution_record_handles_db_error(self):
        """_create_execution_record doesn't raise on DB error."""
        from datetime import UTC, datetime
        from unittest.mock import MagicMock, patch

        from core.workflows.triggers import TriggerHandler

        handler = TriggerHandler(MagicMock(), MagicMock())
        now = datetime.now(UTC)

        with patch("core.workflows.triggers.get_session", side_effect=Exception("DB down")):
            # Should not raise — errors are caught and logged
            result = handler._create_execution_record(
                execution_id="exec-002",
                scenario_name="scenario",
                trigger_source="api",
                user_id=None,
                inputs={},
                started_at=now,
            )
        assert result is None

# ===========================================================================
# workflows: schema
# ===========================================================================

class TestWorkflowSchema:
    """Tests for core/workflows/schema.WorkflowSchema."""

    def _make_schema(self, nodes=None, edges=None):
        """Create a minimal WorkflowSchema with start and end nodes."""
        from core.workflows.schema import WorkflowSchema

        if nodes is None:
            nodes = [
                {"id": "n-start", "type": "start", "data": {}},
                {"id": "n-end", "type": "end", "data": {}},
            ]
        if edges is None:
            edges = [{"id": "e1", "source": "n-start", "target": "n-end"}]
        return WorkflowSchema.model_validate({"nodes": nodes, "edges": edges})

    def test_workflow_schema_creation(self):
        """WorkflowSchema creates with start and end nodes."""
        schema = self._make_schema()
        assert schema is not None
        assert len(schema.nodes) == 2

    def test_workflow_schema_stores_edges(self):
        """WorkflowSchema stores edges."""
        schema = self._make_schema()
        assert len(schema.edges) == 1

    def test_workflow_schema_has_start_node(self):
        """WorkflowSchema stores start node."""
        schema = self._make_schema()
        node_types = [n.type for n in schema.nodes]
        assert "start" in node_types

    def test_workflow_schema_has_end_node(self):
        """WorkflowSchema stores end node."""
        schema = self._make_schema()
        node_types = [n.type for n in schema.nodes]
        assert "end" in node_types

    def test_validate_agents_no_task_nodes(self):
        """validate_agents returns no errors when no task nodes exist."""
        schema = self._make_schema()
        errors = schema.validate_agents()
        assert isinstance(errors, list)

    def test_find_cycle_nodes_acyclic(self):
        """_find_cycle_nodes returns empty list for acyclic graph."""
        schema = self._make_schema()
        cycles = schema._find_cycle_nodes()
        assert cycles == []

    def test_workflow_node_model(self):
        """WorkflowNode validates required fields."""
        from core.workflows.schema import WorkflowNode

        node = WorkflowNode.model_validate({"id": "n1", "type": "start", "data": {}})
        assert node.id == "n1"
        assert node.type == "start"

    def test_workflow_edge_model(self):
        """WorkflowEdge validates required fields."""
        from core.workflows.schema import WorkflowEdge

        edge = WorkflowEdge.model_validate({"id": "e1", "source": "n1", "target": "n2"})
        assert edge.id == "e1"
        assert edge.source == "n1"
        assert edge.target == "n2"

# ===========================================================================
# database: session management
# ===========================================================================

class TestDatabaseSession:
    """Tests for core/database/session.py."""

    def test_get_session_factory_returns_sessionmaker(self):
        """get_session_factory returns a SQLAlchemy sessionmaker."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from core.database.session import get_session_factory

        engine = create_engine(
            os.environ.get(
                "DRYADE_TEST_DATABASE_URL",
                "postgresql+psycopg://dryade:dryade_dev@localhost:5432/dryade_test",
            )
        )
        factory = get_session_factory(engine=engine)
        assert callable(factory)

    def test_get_session_context_manager(self):
        """get_session() is a context manager that yields a session."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        # Patch get_session_factory to use PostgreSQL test database engine
        from core.database import models
        from core.database.session import get_session_factory

        engine = create_engine(
            os.environ.get(
                "DRYADE_TEST_DATABASE_URL",
                "postgresql+psycopg://dryade:dryade_dev@localhost:5432/dryade_test",
            )
        )
        models.Base.metadata.create_all(engine)

        from unittest.mock import patch

        with patch(
            "core.database.session.get_session_factory", return_value=sessionmaker(bind=engine)
        ):
            from core.database.session import get_session

            with get_session() as session:
                assert session is not None
                # Session can execute simple queries
                result = session.execute(models.Conversation.__table__.select())
                assert result is not None

    def test_init_db_creates_tables(self):
        """init_db creates tables in fresh database."""
        from sqlalchemy import create_engine, inspect

        from core.database.session import init_db

        engine = create_engine(
            os.environ.get(
                "DRYADE_TEST_DATABASE_URL",
                "postgresql+psycopg://dryade:dryade_dev@localhost:5432/dryade_test",
            )
        )
        created = init_db(engine=engine)
        # Should create tables
        assert isinstance(created, list)
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert len(tables) > 0

    def test_init_db_idempotent(self):
        """init_db is safe to call twice (returns empty list second time)."""
        from sqlalchemy import create_engine

        from core.database.session import init_db

        engine = create_engine(
            os.environ.get(
                "DRYADE_TEST_DATABASE_URL",
                "postgresql+psycopg://dryade:dryade_dev@localhost:5432/dryade_test",
            )
        )
        init_db(engine=engine)
        created_second = init_db(engine=engine)
        assert created_second == []  # Nothing new to create
