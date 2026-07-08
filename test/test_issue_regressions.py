import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_helpers_utils(testcase):
    """Load helpers/utils.py against a self-contained qgis stub.

    Registers/restores the qgis modules in sys.modules (via the testcase's
    addCleanup) so it does not perturb the fragile shared stubs used by other
    tests in this module.
    """
    import sys
    import types
    import importlib.util

    names = (
        "qgis", "qgis.core", "qgis.PyQt", "qgis.PyQt.QtCore",
        "qgis.PyQt.QtWidgets",
    )
    saved = {n: sys.modules.get(n) for n in names}

    def _restore():
        for n, prev in saved.items():
            if prev is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = prev
    testcase.addCleanup(_restore)

    qgis = types.ModuleType("qgis")
    core = types.ModuleType("qgis.core")
    core.QgsApplication = type("QgsApplication", (), {})
    core.QgsAuthMethodConfig = type("QgsAuthMethodConfig", (), {})
    qgis.core = core
    pyqt = types.ModuleType("qgis.PyQt")
    qtcore = types.ModuleType("qgis.PyQt.QtCore")
    qtcore.QSettings = type("QSettings", (), {})
    pyqt.QtCore = qtcore
    qtwidgets = types.ModuleType("qgis.PyQt.QtWidgets")
    qtwidgets.QMessageBox = type("QMessageBox", (), {})
    pyqt.QtWidgets = qtwidgets
    qgis.PyQt = pyqt
    sys.modules["qgis"] = qgis
    sys.modules["qgis.core"] = core
    sys.modules["qgis.PyQt"] = pyqt
    sys.modules["qgis.PyQt.QtCore"] = qtcore
    sys.modules["qgis.PyQt.QtWidgets"] = qtwidgets

    spec = importlib.util.spec_from_file_location(
        "sfc_utils_under_test", ROOT / "helpers" / "utils.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- Fake QgsExpression AST node classes for the expression compiler tests ---
# These duck-type the PyQGIS node API used by helpers/expression_compiler.py.
# The SAME class objects are injected into the stubbed qgis.core so the
# compiler's isinstance() checks match instances built here.


class _FakeColumnRef:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name


class _FakeLiteral:
    def __init__(self, value):
        self._value = value

    def value(self):
        return self._value


class _FakeBinaryOperator:
    # Enum values mirror QgsExpressionNodeBinaryOperator (exact values are not
    # important as long as they are consistent between here and the compiler).
    boOr = 0
    boAnd = 1
    boEQ = 2
    boNE = 3
    boLE = 4
    boGE = 5
    boLT = 6
    boGT = 7
    boRegexp = 8
    boLike = 9
    boNotLike = 10
    boILike = 11
    boNotILike = 12
    boIs = 13
    boIsNot = 14
    boPlus = 15
    boMinus = 16
    boMul = 17
    boDiv = 18

    def __init__(self, op, left, right):
        self._op = op
        self._left = left
        self._right = right

    def op(self):
        return self._op

    def opLeft(self):
        return self._left

    def opRight(self):
        return self._right


class _FakeUnaryOperator:
    uoNot = 0
    uoMinus = 1

    def __init__(self, op, operand):
        self._op = op
        self._operand = operand

    def op(self):
        return self._op

    def operand(self):
        return self._operand


class _FakeNodeList:
    def __init__(self, nodes):
        self._nodes = nodes

    def list(self):
        return self._nodes


class _FakeInOperator:
    def __init__(self, node, members, is_not=False):
        self._node = node
        self._list = _FakeNodeList(members)
        self._is_not = is_not

    def node(self):
        return self._node

    def list(self):
        return self._list

    def isNotIn(self):
        return self._is_not


class _FakeExpression:
    def __init__(self, text):
        self._text = text

    def hasParserError(self):
        return False

    def rootNode(self):
        return None


class _FakeField:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name


class _FakeFields:
    """Case-insensitive field lookup mirroring QgsFields."""

    def __init__(self, names):
        self._names = list(names)

    def lookupField(self, name):
        for idx, existing in enumerate(self._names):
            if existing.lower() == name.lower():
                return idx
        return -1

    def at(self, idx):
        return _FakeField(self._names[idx])


class _FakeUnsupportedNode:
    """A node type outside the whitelist (e.g. a function)."""


def _load_expression_compiler(testcase):
    """Load the real helpers/expression_compiler.py against a stub qgis.core
    that exposes the AST node classes (but NOT QgsSqlExpressionCompiler).

    This exercises the module's real import list, so it guards against the
    plugin-load crash that occurred when the module depended on the
    unavailable QgsSqlExpressionCompiler binding.
    """
    import sys
    import types
    import importlib.util

    names = ("qgis", "qgis.core", "helpers", "helpers.sql",
             "helpers.expression_compiler")
    saved = {n: sys.modules.get(n) for n in names}

    def _restore():
        for n, prev in saved.items():
            if prev is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = prev
    testcase.addCleanup(_restore)

    qgis = types.ModuleType("qgis")
    core = types.ModuleType("qgis.core")
    core.QgsExpression = _FakeExpression
    core.QgsExpressionNodeBinaryOperator = _FakeBinaryOperator
    core.QgsExpressionNodeColumnRef = _FakeColumnRef
    core.QgsExpressionNodeInOperator = _FakeInOperator
    core.QgsExpressionNodeLiteral = _FakeLiteral
    core.QgsExpressionNodeUnaryOperator = _FakeUnaryOperator
    core.QgsFields = _FakeFields
    qgis.core = core
    sys.modules["qgis"] = qgis
    sys.modules["qgis.core"] = core

    # Register a "helpers" package rooted at the real folder so the module's
    # relative "from .sql import ..." resolves to the real (pure-Python) sql.py.
    helpers_pkg = types.ModuleType("helpers")
    helpers_pkg.__path__ = [str(ROOT / "helpers")]
    sys.modules["helpers"] = helpers_pkg
    sys.modules.pop("helpers.sql", None)

    spec = importlib.util.spec_from_file_location(
        "helpers.expression_compiler", ROOT / "helpers" / "expression_compiler.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["helpers.expression_compiler"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestExpressionCompilerCompilation(unittest.TestCase):
    """Behavioral + import-safety tests for the pure-Python AST compiler."""

    def setUp(self):
        self.mod = _load_expression_compiler(self)
        self.fields = _FakeFields(["POP", "NAME", "ID"])

    def _compile(self, node):
        return self.mod._compile_node(node, self.fields)

    def test_module_imports_without_qgs_sql_expression_compiler(self):
        # The mere fact setUp() loaded the module under a qgis.core that does
        # NOT define QgsSqlExpressionCompiler proves the import bug is gone.
        self.assertTrue(hasattr(self.mod, "compile_expression_to_sql"))

    def test_equality_compiles_with_quoting(self):
        node = _FakeBinaryOperator(
            _FakeBinaryOperator.boEQ, _FakeColumnRef("POP"), _FakeLiteral(1000)
        )
        self.assertEqual(self._compile(node), "(POP = 1000)")

    def test_and_of_predicates_compiles(self):
        node = _FakeBinaryOperator(
            _FakeBinaryOperator.boAnd,
            _FakeBinaryOperator(
                _FakeBinaryOperator.boGT, _FakeColumnRef("POP"), _FakeLiteral(1000)
            ),
            _FakeBinaryOperator(
                _FakeBinaryOperator.boILike,
                _FakeColumnRef("NAME"),
                _FakeLiteral("A%"),
            ),
        )
        self.assertEqual(
            self._compile(node), "((POP > 1000) AND (NAME ILIKE 'A%'))"
        )

    def test_or_of_predicates_compiles(self):
        node = _FakeBinaryOperator(
            _FakeBinaryOperator.boOr,
            _FakeBinaryOperator(
                _FakeBinaryOperator.boEQ, _FakeColumnRef("ID"), _FakeLiteral(1)
            ),
            _FakeBinaryOperator(
                _FakeBinaryOperator.boEQ, _FakeColumnRef("ID"), _FakeLiteral(2)
            ),
        )
        self.assertEqual(
            self._compile(node), "((ID = 1) OR (ID = 2))"
        )

    def test_in_operator_compiles(self):
        node = _FakeInOperator(
            _FakeColumnRef("ID"), [_FakeLiteral(1), _FakeLiteral(2)]
        )
        self.assertEqual(self._compile(node), "(ID IN (1, 2))")

    def test_not_in_operator_compiles(self):
        node = _FakeInOperator(
            _FakeColumnRef("ID"), [_FakeLiteral(1)], is_not=True
        )
        self.assertEqual(self._compile(node), "(ID NOT IN (1))")

    def test_not_unary_compiles(self):
        node = _FakeUnaryOperator(
            _FakeUnaryOperator.uoNot,
            _FakeBinaryOperator(
                _FakeBinaryOperator.boEQ, _FakeColumnRef("POP"), _FakeLiteral(1)
            ),
        )
        self.assertEqual(self._compile(node), "(NOT (POP = 1))")

    def test_string_literal_is_escaped(self):
        node = _FakeBinaryOperator(
            _FakeBinaryOperator.boEQ,
            _FakeColumnRef("NAME"),
            _FakeLiteral("x'); DROP TABLE t;--"),
        )
        compiled = self._compile(node)
        self.assertEqual(compiled, "(NAME = 'x''); DROP TABLE t;--')")

    def test_null_and_bool_literals(self):
        is_null = _FakeBinaryOperator(
            _FakeBinaryOperator.boIs, _FakeColumnRef("NAME"), _FakeLiteral(None)
        )
        self.assertEqual(self._compile(is_null), "(NAME IS NULL)")
        is_true = _FakeBinaryOperator(
            _FakeBinaryOperator.boEQ, _FakeColumnRef("ID"), _FakeLiteral(True)
        )
        self.assertEqual(self._compile(is_true), "(ID = TRUE)")

    def test_unknown_column_returns_none(self):
        node = _FakeBinaryOperator(
            _FakeBinaryOperator.boEQ, _FakeColumnRef("SECRET"), _FakeLiteral(1)
        )
        self.assertIsNone(self._compile(node))

    def test_unsupported_binary_operator_returns_none(self):
        node = _FakeBinaryOperator(
            _FakeBinaryOperator.boPlus, _FakeColumnRef("POP"), _FakeLiteral(1)
        )
        self.assertIsNone(self._compile(node))

    def test_unsupported_node_type_returns_none(self):
        self.assertIsNone(self._compile(_FakeUnsupportedNode()))

    def test_unary_minus_returns_none(self):
        node = _FakeUnaryOperator(
            _FakeUnaryOperator.uoMinus, _FakeLiteral(1)
        )
        self.assertIsNone(self._compile(node))

    def test_in_with_uncompilable_member_returns_none(self):
        node = _FakeInOperator(
            _FakeColumnRef("ID"), [_FakeLiteral(1), _FakeUnsupportedNode()]
        )
        self.assertIsNone(self._compile(node))

    def test_compile_expression_to_sql_guards_empty_and_none(self):
        self.assertIsNone(
            self.mod.compile_expression_to_sql("", self.fields)
        )
        self.assertIsNone(
            self.mod.compile_expression_to_sql("x", None)
        )


class TestIssueRegressions(unittest.TestCase):
    def test_utils_uses_importlib_metadata(self):
        content = (ROOT / "helpers" / "utils.py").read_text(encoding="utf-8")
        self.assertIn("import importlib.metadata", content)

    def test_vector_provider_reload_resets_caches(self):
        content = (ROOT / "providers" / "sf_vector_data_provider.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("self._feature_count = None", content)
        self.assertIn("self._extent = None", content)

    def test_browser_queries_use_case_insensitive_filters(self):
        content = (ROOT / "entities" / "sf_data_item.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("table_catalog ILIKE", content)
        self.assertIn("TABLE_SCHEMA ILIKE", content)
        self.assertIn("TABLE_NAME ILIKE", content)

    def test_browser_shows_non_geo_tables(self):
        """Geo-type filter should only apply at column level, not schema/table level."""
        content = (ROOT / "entities" / "sf_data_item.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('if self.item_type == "table":', content)
        self.assertIn("geo_type_filter", content)
        self.assertIn("not self.geom_column", content)

    def test_export_algorithm_has_geometry_insert_sql(self):
        content = (ROOT / "qgis_snowflake_connector_algorithm.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("def get_geometry_insert_sql(", content)
        self.assertIn("ST_GEOGFROMWKB(TO_BINARY", content)
        self.assertIn("ST_SETSRID(ST_GEOMETRYFROMWKB", content)

    def test_export_select_projection_applies_geometry_conversion(self):
        """The SELECT projection must wrap the geometry alias with spatial functions."""
        content = (ROOT / "qgis_snowflake_connector_algorithm.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("ST_GEOGFROMWKB(TO_BINARY(v.", content)
        self.assertIn("ST_SETSRID(ST_GEOMETRYFROMWKB(TO_BINARY(v.", content)

    def test_export_values_null_for_empty_geometry(self):
        """Empty hex_string must produce NULL in the VALUES tuple, not empty string."""
        content = (ROOT / "qgis_snowflake_connector_algorithm.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('if hex_string == "":', content)
        self.assertIn('query += "(NULL"', content)

    def test_data_source_provider_uses_set_subtype(self):
        content = (ROOT / "providers" / "sf_data_source_provider.py").read_text(
            encoding="utf-8"
        )
        # The subtype is preserved via the version-compatible helper
        # (issue #120): create_qgs_field applies setSubType internally.
        self.assertIn("sub_type=subType", content)
        self.assertIn("create_qgs_field(", content)

    def test_export_blocks_same_snowflake_table(self):
        """Export must refuse when target table matches the input layer's
        source Snowflake table, since it would duplicate every row."""
        content = (ROOT / "qgis_snowflake_connector_algorithm.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("SAME_TABLE_EXPORT_MESSAGE", content)
        self.assertIn("same Snowflake table", content)
        self.assertIn("def _targets_same_snowflake_table(", content)
        self.assertIn("parse_uri", content)
        # checkParameterValues guard (returns False with the message)
        self.assertIn(
            "return False, SAME_TABLE_EXPORT_MESSAGE", content
        )
        # processAlgorithm guard (raises QgsProcessingException)
        self.assertIn(
            "raise QgsProcessingException(SAME_TABLE_EXPORT_MESSAGE)", content
        )


class TestSQLSafety(unittest.TestCase):
    """Tests for Track 1: centralized SQL quoting."""

    def test_sql_helpers_exist(self):
        content = (ROOT / "helpers" / "sql.py").read_text(encoding="utf-8")
        self.assertIn("def quote_identifier(", content)
        self.assertIn("def quote_literal(", content)
        self.assertIn("def qualified_table_name(", content)

    def test_quote_identifier_basic(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "helpers.sql", ROOT / "helpers" / "sql.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        self.assertEqual(mod.quote_identifier("foo"), 'foo')
        self.assertEqual(mod.quote_identifier("FOO_BAR"), 'FOO_BAR')
        self.assertEqual(mod.quote_identifier('foo"bar'), '"foo""bar"')
        self.assertEqual(mod.quote_identifier("col name"), '"col name"')
        self.assertEqual(mod.quote_identifier(""), '""')
        self.assertEqual(mod.quote_identifier('"already_quoted"'), '"already_quoted"')

    def test_quote_literal_basic(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "helpers.sql", ROOT / "helpers" / "sql.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        self.assertEqual(mod.quote_literal("foo"), "'foo'")
        self.assertEqual(mod.quote_literal("it's"), "'it''s'")

    def test_quote_literal_escapes_backslash(self):
        """SNOW-3712090 / SNOW-3712092: Snowflake treats backslash as an escape
        character in string literals, so quote_literal must double backslashes
        to stop a trailing-backslash / \\' breakout of the single-quoted
        literal."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "helpers.sql", ROOT / "helpers" / "sql.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # A lone backslash must be doubled.
        self.assertEqual(mod.quote_literal("a\\b"), "'a\\\\b'")
        # The classic breakout payload: \' UNION SELECT ... --
        out = mod.quote_literal("\\' UNION SELECT CURRENT_ROLE() --")
        self.assertEqual(out, "'\\\\'' UNION SELECT CURRENT_ROLE() --'")
        # There must be no single backslash immediately before the closing
        # quote (which Snowflake would read as an escaped, non-terminating
        # quote). Every backslash in the interior must be doubled.
        interior = out[1:-1]
        self.assertNotIn("'", interior.replace("''", ""))
        self.assertNotIn("\\", interior.replace("\\\\", ""))

    def test_quote_json_literal_for_parse_json_prefers_dollar_quotes(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "helpers.sql", ROOT / "helpers" / "sql.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        payload = '{"name":"O\'Brien"}'
        self.assertEqual(
            mod.quote_json_literal_for_parse_json(payload),
            f"$${payload}$$",
        )

    def test_quote_json_literal_for_parse_json_strict_raises_when_delimiter_present(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "helpers.sql", ROOT / "helpers" / "sql.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        payload = '{"k":"contains $$ delimiter and it\'s ok"}'
        with self.assertRaises(ValueError):
            mod.quote_json_literal_for_parse_json(payload)

    def test_predicate_has_statement_breakers(self):
        """SNOW-3712086: the free-text WHERE-clause guard must flag comments,
        statement terminators and set operators, while allowing a plain
        boolean predicate."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "helpers.sql", ROOT / "helpers" / "sql.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        for bad in [
            "1=0 UNION ALL SELECT SSN FROM PROD.HR.EMPLOYEES --",
            "POP > 1 ; DROP TABLE T",
            "POP > 1 /* comment */",
            "a INTERSECT SELECT 1",
            "a EXCEPT SELECT 1",
        ]:
            self.assertTrue(
                mod.predicate_has_statement_breakers(bad),
                f"should flag: {bad!r}",
            )
        for ok in ["POP > 1000", "STATE = 'CA' AND POP >= 100", "", None]:
            self.assertFalse(
                mod.predicate_has_statement_breakers(ok),
                f"should allow: {ok!r}",
            )

    def test_qualified_table_name(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "helpers.sql", ROOT / "helpers" / "sql.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        self.assertEqual(
            mod.qualified_table_name("DB", "SCH", "TBL"),
            'DB.SCH.TBL',
        )
        self.assertEqual(
            mod.qualified_table_name("my db", "SCH", "TBL"),
            '"my db".SCH.TBL',
        )

    def test_data_base_uses_quote_helpers(self):
        content = (ROOT / "helpers" / "data_base.py").read_text(encoding="utf-8")
        self.assertIn("from ..helpers.sql import", content)
        self.assertIn("quote_literal(", content)
        self.assertIn("quote_identifier(", content)

    def test_algorithm_uses_quote_helpers(self):
        content = (ROOT / "qgis_snowflake_connector_algorithm.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("from .helpers.sql import", content)
        self.assertIn("qualified_table_name(", content)
        self.assertIn("quote_literal(", content)
        self.assertIn("PARSE_JSON(v.", content)
        self.assertNotIn("replace(\"'\", \"\\\\'\")", content)

    def test_algorithm_variant_insert_uses_select_over_values_alias(self):
        content = (ROOT / "qgis_snowflake_connector_algorithm.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("SELECT {','.join(select_projection)} FROM VALUES", content)
        self.assertIn("AS v({','.join(value_aliases)})", content)
        self.assertIn("PARSE_JSON(v.{alias})", content)

    def test_feature_iterator_uses_quote_identifier(self):
        content = (ROOT / "providers" / "sf_feature_iterator.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("from ..helpers.sql import quote_identifier", content)
        self.assertIn("quote_identifier(", content)

    def test_vector_provider_uses_quote_helpers(self):
        content = (ROOT / "providers" / "sf_vector_data_provider.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("from ..helpers.sql import", content)
        self.assertIn("quote_identifier(", content)

    def test_connection_manager_uses_quote_identifier(self):
        content = (ROOT / "managers" / "sf_connection_manager.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("from ..helpers.sql import quote_identifier", content)

    def test_dialogs_use_quote_helpers(self):
        content_table = (ROOT / "dialogs" / "sf_new_table_dialog.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("qualified_table_name(", content_table)
        content_schema = (ROOT / "dialogs" / "sf_new_schema_dialog.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("quote_identifier(", content_schema)


class TestQuoteIdentifierInjection(unittest.TestCase):
    """SNOW-3712084: quote_identifier() must never let an attacker-controlled
    identifier break out of the quoted-identifier context.

    Root cause: the original fast-path returned any value that merely started
    and ended with a double quote VERBATIM, without verifying the interior was
    a single well-formed quoted identifier. That allowed second-order SQL
    injection through Snowflake object names and .qgs URI components
    (SNOW-3712077 / 81 / 85 / 88 / 89 / 91 / 93 all flow through this helper).
    """

    @staticmethod
    def _load_module():
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "helpers.sql", ROOT / "helpers" / "sql.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    @staticmethod
    def _is_safe_identifier(out):
        """A safe result is either a bare simple identifier or a single,
        well-formed quoted identifier (all interior quotes doubled)."""
        if re.match(r"^[A-Za-z_][A-Za-z0-9_$]*$", out):
            return True
        if len(out) >= 2 and out.startswith('"') and out.endswith('"'):
            return '"' not in out[1:-1].replace('""', "")
        return False

    # Payloads lifted from the Mythos Zero findings; each begins and ends
    # with a double quote but hides an un-doubled interior quote that breaks
    # out of the identifier context (i.e. it is NOT a well-formed quoted
    # identifier and must be re-escaped rather than passed through).
    _MALICIOUS = [
        '"X" AS SELECT * FROM SECRETS--"',
        '"PUBLIC"."CUSTOMERS"(X INT)--"',
        '"ALICE_LZ"."LOOT" AS SELECT * FROM PROD.SECRETS.KEYS--"',
        '"X") FROM TABLE(GENERATOR(ROWCOUNT=>1e10)) --"',
        '"X")) , (1) /*"',
        '"G") IN (SELECT 1)) UNION ALL SELECT PASSWORD FROM USERS--"',
    ]

    def test_malicious_quoted_identifiers_are_neutralized(self):
        mod = self._load_module()
        for payload in self._MALICIOUS:
            out = mod.quote_identifier(payload)
            self.assertTrue(
                self._is_safe_identifier(out),
                f"quote_identifier failed to neutralize breakout payload "
                f"{payload!r} -> {out!r}",
            )
            self.assertNotEqual(
                out, payload,
                f"quote_identifier passed malicious payload through "
                f"verbatim: {payload!r}",
            )

    def test_wellformed_quoted_identifier_preserved(self):
        """Legitimate, already-correctly-quoted identifiers must round-trip
        unchanged so existing callers keep working."""
        mod = self._load_module()
        self.assertEqual(mod.quote_identifier('"already_quoted"'), '"already_quoted"')
        self.assertEqual(mod.quote_identifier('"with""doubled"'), '"with""doubled"')
        self.assertEqual(mod.quote_identifier('"col name"'), '"col name"')

    def test_plain_identifiers_still_quote_correctly(self):
        mod = self._load_module()
        self.assertEqual(mod.quote_identifier("foo"), "foo")
        self.assertEqual(mod.quote_identifier('foo"bar'), '"foo""bar"')


class TestPhase2SQLInjectionCallSites(unittest.TestCase):
    """Phase 2: individual call sites that fed attacker-controlled values into
    SQL without routing them through the centralized quoting helpers."""

    def test_get_type_from_table_geo_column_quotes_from_clause(self):
        """SNOW-3712081: the table_name forwarded as the FROM clause must be
        quoted, otherwise a stored TABLE_NAME can splice raw SQL into FROM."""
        content = (ROOT / "helpers" / "data_base.py").read_text(encoding="utf-8")
        idx = content.index("def get_type_from_table_geo_column(")
        next_def = content.index("\ndef ", idx + 1)
        body = content[idx:next_def]
        self.assertIn("from_clause=quote_identifier(table_name)", body)
        self.assertNotIn("from_clause=table_name", body)

    def test_geometry_type_escaped_in_extent_query(self):
        """SNOW-3712085: _geometry_type comes from the (project-file) URI and
        must be escaped as a literal, not interpolated inside raw quotes. The
        escaping now lives in the shared _geometry_type_filter() helper, which
        both featureCount() and extent() delegate to."""
        content = (ROOT / "providers" / "sf_vector_data_provider.py").read_text(
            encoding="utf-8"
        )
        idx = content.index("def _geometry_type_filter(self)")
        next_def = content.index("\n    def ", idx + 1)
        helper_body = content[idx:next_def]
        self.assertIn("self._geometry_type", helper_body)
        self.assertIn("quote_literal(", helper_body)
        self.assertNotIn("ILIKE '{self._geometry_type}'", content)

    def test_geometry_type_escaped_in_feature_iterator(self):
        """SNOW-3712085: same URI-controlled value reused in the iterator's
        inner WHERE IN (...) list must be escaped via quote_literal."""
        content = (ROOT / "providers" / "sf_feature_iterator.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("quote_literal(self._provider._geometry_type)", content)
        self.assertNotIn("IN ('{self._provider._geometry_type}'", content)


class TestPhase3PredicateInjection(unittest.TestCase):
    """Phase 3: raw SQL predicates / QGIS expressions must not reach Snowflake
    verbatim (SNOW-3712078 / SNOW-3712093 / SNOW-3712086)."""

    def test_expression_compiler_is_fail_safe(self):
        content = (ROOT / "helpers" / "expression_compiler.py").read_text(
            encoding="utf-8"
        )
        # QgsSqlExpressionCompiler is NOT exposed in PyQGIS; the module must not
        # depend on it (that dependency crashed plugin load).
        self.assertNotIn("QgsSqlExpressionCompiler", content)
        # Compilation walks the QgsExpression AST and fails closed to None.
        self.assertIn("rootNode()", content)
        self.assertIn("def compile_expression_to_sql(", content)
        # Values/identifiers routed through the safe helpers.
        self.assertIn("quote_identifier", content)
        self.assertIn("quote_literal", content)

    def test_feature_iterator_compiles_filter_expression(self):
        """SNOW-3712078: the iterator must compile the filter expression and
        must NOT run the old raw validation query or append raw expression."""
        content = (ROOT / "providers" / "sf_feature_iterator.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("from ..helpers.expression_compiler import compile_expression_to_sql", content)
        self.assertIn("compile_expression_to_sql(", content)
        # The raw-text pushdown patterns must be gone.
        self.assertNotIn("where_clause_list.append(expression)", content)
        self.assertNotIn('.replace(\'"\', "")', content)

    def test_provider_subset_string_is_compiled(self):
        """SNOW-3712093: setSubsetString must compile/validate rather than
        execute the raw predicate as a probe."""
        content = (ROOT / "providers" / "sf_vector_data_provider.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("compile_expression_to_sql(", content)
        idx = content.index("def setSubsetString(")
        next_def = content.index("\n    def ", idx + 1)
        body = content[idx:next_def]
        self.assertIn("compile_expression_to_sql(subsetstring", body)
        self.assertNotIn("WHERE {subsetstring} LIMIT 0", body)

    def test_import_where_clause_is_guarded(self):
        """SNOW-3712086: the free-text WHERE clause must be validated before it
        is concatenated into the SELECT."""
        content = (ROOT / "processing" / "import_from_snowflake.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("predicate_has_statement_breakers", content)
        self.assertIn("QgsProcessingException", content)
        guard_idx = content.index("predicate_has_statement_breakers(where)")
        append_idx = content.index('sql += f" WHERE {where}"')
        self.assertLess(
            guard_idx, append_idx,
            "WHERE clause must be validated before being appended",
        )


class TestPhase4ProjectFileTrust(unittest.TestCase):
    """Phase 4: values restored verbatim from an (untrusted) .qgs/.qgz project
    must be re-validated before they can cause harm."""

    def test_sql_query_layer_is_row_capped(self):
        """SNOW-3712076: the custom sql_query layer branch must also compute
        _is_limited_unordered (row cap), not leave it at the default False."""
        content = (ROOT / "providers" / "sf_vector_data_provider.py").read_text(
            encoding="utf-8"
        )
        start = content.index("if self._sql_query and not self._table_name:")
        end = content.index("self.get_geometry_column()", start)
        block = content[start:end]
        # Both the sql_query branch and the table branch must size-check.
        self.assertEqual(
            block.count("check_from_clause_exceeds_size"), 2,
            "sql_query branch must also probe size via check_from_clause_exceeds_size",
        )
        self.assertIn("SNOW-3712076", block)

    def test_iterator_close_releases_cursor(self):
        """SNOW-3712076: close() must release the server-side cursor."""
        content = (ROOT / "providers" / "sf_feature_iterator.py").read_text(
            encoding="utf-8"
        )
        idx = content.index("def close(self)")
        body = content[idx:idx + 500]
        self.assertIn("result.close()", body)
        self.assertIn("self._result = None", body)

    def test_capabilities_gate_on_limited_unordered(self):
        """SNOW-3712082: edit/SelectAtId capabilities must be withheld when the
        result set is a random-sampled/unordered set (unstable feature ids)."""
        content = (ROOT / "providers" / "sf_vector_data_provider.py").read_text(
            encoding="utf-8"
        )
        idx = content.index("def capabilities(self)")
        next_def = content.index("\n    def ", idx + 1)
        body = content[idx:next_def]
        self.assertIn("self._is_limited_unordered", body)

    def test_capabilities_revalidate_primary_key(self):
        """SNOW-3712083: capabilities must re-validate the URI primary key
        uniqueness before granting edit capabilities."""
        content = (ROOT / "providers" / "sf_vector_data_provider.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("def _validate_primary_key(self)", content)
        self.assertIn("get_declared_primary_key", content)
        self.assertIn("check_column_has_duplicates", content)
        idx = content.index("def capabilities(self)")
        next_def = content.index("\n    def ", idx + 1)
        body = content[idx:next_def]
        self.assertIn("_validate_primary_key()", body)


class TestPhase4AuthcfgUri(unittest.TestCase):
    """SNOW-3712094: the connection alias must be hidden behind an authcfg=
    token in persisted URIs, and resolved back on load."""

    def _load_utils(self):
        return _load_helpers_utils(self)

    def test_decode_uri_supports_legacy_connection_name(self):
        mod = self._load_utils()
        params = mod.decodeUri("connection_name=myconn table_name=T srid=4326")
        self.assertEqual(params.get("connection_name"), "myconn")

    def test_decode_uri_resolves_authcfg_to_connection_name(self):
        mod = self._load_utils()
        mod.resolve_authcfg_connection_name = (
            lambda cid: "resolved_conn" if cid == "ABC1234" else None
        )
        params = mod.decodeUri("authcfg=ABC1234 table_name=T srid=4326")
        self.assertEqual(params.get("authcfg"), "ABC1234")
        self.assertEqual(params.get("connection_name"), "resolved_conn")

    def test_decode_uri_authcfg_unresolvable_leaves_no_connection(self):
        # A project opened on a foreign machine: the id does not resolve, so no
        # connection_name is injected -> parse_uri will later reject it.
        mod = self._load_utils()
        mod.resolve_authcfg_connection_name = lambda cid: None
        params = mod.decodeUri("authcfg=NOPE table_name=T srid=4326")
        self.assertNotIn("connection_name", params)

    def test_connection_uri_token_prefers_authcfg(self):
        mod = self._load_utils()
        mod.get_or_create_connection_authcfg = lambda name: "XYZ7890"
        self.assertEqual(mod.connection_uri_token("myconn"), "authcfg=XYZ7890")

    def test_connection_uri_token_falls_back_to_connection_name(self):
        mod = self._load_utils()
        mod.get_or_create_connection_authcfg = lambda name: None
        self.assertEqual(
            mod.connection_uri_token("myconn"), "connection_name=myconn"
        )

    def test_datasource_uri_honors_expand_auth_config(self):
        content = (ROOT / "providers" / "sf_vector_data_provider.py").read_text(
            encoding="utf-8"
        )
        idx = content.index("def dataSourceUri(self")
        next_def = content.index("\n    def ", idx + 1)
        body = content[idx:next_def]
        self.assertIn("expandAuthConfig", body)
        self.assertIn("authcfg=", body)
        self.assertIn("get_or_create_connection_authcfg", body)
        self.assertIn("_replace_connection_token", body)
        # The redacted branch must be guarded by the expandAuthConfig flag
        # rather than unconditionally returning the alias-bearing uri.
        self.assertIn("if expandAuthConfig:", body)

    def test_uri_builders_use_redacted_token(self):
        task = (ROOT / "tasks" / "sf_convert_column_to_layer_task.py").read_text(
            encoding="utf-8"
        )
        meta = (ROOT / "providers" / "sf_metadata_provider.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("connection_uri_token(", task)
        self.assertIn("connection_uri_token(", meta)


class TestPhase5Hardening(unittest.TestCase):
    """Phase 5: cleartext credentials, forced-SMB rich text, arbitrary SQL."""

    def test_no_geom_dialog_forces_plain_text(self):
        """SNOW-3712087: the server-controlled table name must be shown as plain
        text so a <img src=UNC> name cannot trigger an SMB/NTLM leak."""
        content = (ROOT / "entities" / "sf_data_item.py").read_text(
            encoding="utf-8"
        )
        idx = content.index('if self.item_type == "table_no_geom":')
        block = content[idx:idx + 900]
        self.assertIn("setTextFormat(Qt.TextFormat.PlainText)", block)
        # The vulnerable auto-format static call must be gone from this branch.
        self.assertNotIn("QMessageBox.information(", block)

    def test_dialog_skips_cleartext_password_when_encrypted(self):
        """SNOW-3712079: the dialog must not capture the Basic-tab password when
        the encrypted Configurations tab is selected."""
        content = (
            ROOT / "dialogs" / "sf_connection_string_dialog.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'if is_default_auth and not config_tab_selected:', content
        )

    def test_set_connection_settings_clears_password_when_encrypted(self):
        """SNOW-3712079: saving an encrypted Default-Auth connection (no
        password provided) must remove any stale cleartext password rather than
        crash or leave it behind."""
        mod = _load_helpers_utils(self)

        class _FakeSettings:
            def __init__(self):
                self.values = {}
                self.removed = []

            def beginGroup(self, *_):
                pass

            def endGroup(self):
                pass

            def sync(self):
                pass

            def setValue(self, key, value):
                self.values[key] = value

            def remove(self, key):
                self.removed.append(key)

        fake = _FakeSettings()
        mod.get_qsettings = lambda: fake
        mod.set_connection_settings({
            "name": "conn1",
            "warehouse": "WH",
            "account": "ACC",
            "database": "DB",
            "username": "user",
            "connection_type": "Default Authentication",
            "password_encrypted": True,
            "config_id": "abc123",
        })
        self.assertNotIn("password", fake.values)
        self.assertIn("password", fake.removed)

    def test_set_connection_settings_writes_password_when_plaintext(self):
        """Guard rail: legacy plaintext Default-Auth still stores the password."""
        mod = _load_helpers_utils(self)

        class _FakeSettings:
            def __init__(self):
                self.values = {}
                self.removed = []

            def beginGroup(self, *_):
                pass

            def endGroup(self):
                pass

            def sync(self):
                pass

            def setValue(self, key, value):
                self.values[key] = value

            def remove(self, key):
                self.removed.append(key)

        fake = _FakeSettings()
        mod.get_qsettings = lambda: fake
        mod.set_connection_settings({
            "name": "conn1",
            "warehouse": "WH",
            "account": "ACC",
            "database": "DB",
            "username": "user",
            "connection_type": "Default Authentication",
            "password_encrypted": False,
            "password": "s3cret",
        })
        self.assertEqual(fake.values.get("password"), "s3cret")

    def _load_execute_sql(self, iface_value):
        import sys
        import types
        import importlib.util

        names = (
            "qgis", "qgis.core", "qgis.PyQt", "qgis.PyQt.QtCore",
            "qgis.PyQt.QtGui", "qgis.utils",
        )
        saved = {n: sys.modules.get(n) for n in names}

        def _restore():
            for n, prev in saved.items():
                if prev is None:
                    sys.modules.pop(n, None)
                else:
                    sys.modules[n] = prev
        self.addCleanup(_restore)

        qgis = types.ModuleType("qgis")
        core = types.ModuleType("qgis.core")
        for nm in (
            "QgsProcessingAlgorithm", "QgsProcessingParameterString",
            "QgsProcessingOutputString",
        ):
            setattr(core, nm, type(nm, (), {}))
        core.QgsProcessingException = type(
            "QgsProcessingException", (Exception,), {}
        )
        qgis.core = core
        pyqt = types.ModuleType("qgis.PyQt")
        qtcore = types.ModuleType("qgis.PyQt.QtCore")
        qtcore.QCoreApplication = type("QCoreApplication", (), {})
        qtgui = types.ModuleType("qgis.PyQt.QtGui")
        qtgui.QIcon = type("QIcon", (), {})
        pyqt.QtCore = qtcore
        pyqt.QtGui = qtgui
        qgis.PyQt = pyqt
        utils = types.ModuleType("qgis.utils")
        utils.iface = iface_value
        sys.modules["qgis"] = qgis
        sys.modules["qgis.core"] = core
        sys.modules["qgis.PyQt"] = pyqt
        sys.modules["qgis.PyQt.QtCore"] = qtcore
        sys.modules["qgis.PyQt.QtGui"] = qtgui
        sys.modules["qgis.utils"] = utils

        spec = importlib.util.spec_from_file_location(
            "sfc_execute_sql_under_test", ROOT / "processing" / "execute_sql.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_execute_sql_headless_proceeds_without_prompt(self):
        """SNOW-3712080: headless (no iface) runs are user-initiated and proceed."""
        mod = self._load_execute_sql(iface_value=None)
        alg = mod.ExecuteSQLAlgorithm()
        self.assertTrue(alg._confirm_execution("conn", "SELECT 1"))

    def test_execute_sql_requires_confirmation_before_execution(self):
        """SNOW-3712080: the algorithm must gate execution on _confirm_execution
        and abort with QgsProcessingException when declined."""
        content = (ROOT / "processing" / "execute_sql.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("FlagNoThreading", content)
        idx = content.index("def processAlgorithm(")
        body = content[idx:]
        confirm_pos = body.index("_confirm_execution(")
        exec_pos = body.index("mgr.execute_query(")
        self.assertLess(
            confirm_pos, exec_pos,
            "confirmation must happen before the SQL is executed",
        )
        self.assertIn("QgsProcessingException(", body)
        self.assertIn("setTextFormat(Qt.TextFormat.PlainText)", content)


class TestProviderLifecycle(unittest.TestCase):
    """Tests for Track 3: provider cache correctness and geometry handling."""

    def test_reload_data_resets_feature_caches(self):
        """reloadData() must clear features, count, extent but preserve _fields."""
        content = (ROOT / "providers" / "sf_vector_data_provider.py").read_text(
            encoding="utf-8"
        )
        idx = content.index("def reloadData(self)")
        next_def = content.index("\n    def ", idx + 1)
        body = content[idx:next_def]
        self.assertIn("self._features = []", body)
        self.assertIn("self._features_loaded = False", body)
        self.assertIn("self._feature_count = None", body)
        self.assertIn("self._extent = None", body)
        self.assertNotIn("self._fields = None", body,
                         "reloadData must NOT reset _fields to preserve column order")
        self.assertIn("self.connect_database()", body)

    def test_fields_query_filters_by_schema(self):
        """fields() INFORMATION_SCHEMA query must include table_schema ILIKE filter."""
        content = (ROOT / "providers" / "sf_vector_data_provider.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("table_schema ILIKE", content)

    def test_fields_query_filters_by_catalog_and_distinct(self):
        """fields() INFORMATION_SCHEMA query must scope to TABLE_CATALOG and
        use SELECT DISTINCT so same-named tables in other databases or schemas
        cannot contribute duplicated column entries to the layer's field list.
        """
        content = (ROOT / "providers" / "sf_vector_data_provider.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("table_catalog ILIKE", content)
        self.assertIn("SELECT DISTINCT column_name", content)

    def test_feature_iterator_logs_errors(self):
        """fetchFeature() must log attribute errors via QgsMessageLog, not print()."""
        content = (ROOT / "providers" / "sf_feature_iterator.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("QgsMessageLog.logMessage(", content)
        self.assertNotIn(
            'print(\n                                    f"Feature Iterator Error',
            content,
        )

    def test_subset_string_triggers_reload(self):
        """setSubsetString with updateFeatureCount must call reloadData."""
        content = (ROOT / "providers" / "sf_vector_data_provider.py").read_text(
            encoding="utf-8"
        )
        idx = content.index("def setSubsetString(")
        next_def = content.index("\n    def ", idx + 1)
        body = content[idx:next_def]
        self.assertIn("self._feature_count = None", body)
        self.assertIn("self.reloadData()", body)

    def test_geometry_insert_sql_null_handling(self):
        """get_geometry_insert_sql must return 'NULL' for empty hex strings."""
        content = (ROOT / "qgis_snowflake_connector_algorithm.py").read_text(
            encoding="utf-8"
        )
        idx = content.index("def get_geometry_insert_sql(")
        next_def = content.index("\n    def ", idx + 1) if "\n    def " in content[idx + 1:] else len(content)
        body = content[idx:next_def]
        self.assertIn('if hex_string == "":', body)
        self.assertIn('return "NULL"', body)

    def test_geometry_insert_sql_geography_path(self):
        content = (ROOT / "qgis_snowflake_connector_algorithm.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("ST_GEOGFROMWKB(TO_BINARY(", content)

    def test_geometry_insert_sql_geometry_path(self):
        content = (ROOT / "qgis_snowflake_connector_algorithm.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("ST_SETSRID(ST_GEOMETRYFROMWKB(TO_BINARY(", content)

    def test_limits_constants_exist(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "helpers.limits", ROOT / "helpers" / "limits.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        self.assertEqual(mod.DEFAULT_ROW_LIMIT, 50_000)
        self.assertEqual(mod.H3_ROW_LIMIT, 500_000)
        self.assertIn("NUMBER", mod.H3_COLUMN_TYPES)
        self.assertIn("TEXT", mod.H3_COLUMN_TYPES)
        self.assertIn("H3GEO", mod.H3_COLUMN_TYPES)

    def test_limits_function_uses_constants(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "helpers.limits", ROOT / "helpers" / "limits.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        self.assertEqual(mod.limit_size_for_type("GEOGRAPHY"), mod.DEFAULT_ROW_LIMIT)
        self.assertEqual(mod.limit_size_for_type("GEOMETRY"), mod.DEFAULT_ROW_LIMIT)
        self.assertEqual(mod.limit_size_for_type("NUMBER"), mod.H3_ROW_LIMIT)
        self.assertEqual(mod.limit_size_for_type("TEXT"), mod.H3_ROW_LIMIT)
        self.assertEqual(mod.limit_size_for_type("H3GEO"), mod.H3_ROW_LIMIT)

    def test_feature_iterator_uses_limits_import(self):
        content = (ROOT / "providers" / "sf_feature_iterator.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("from ..helpers.limits import limit_size_for_type", content)


class TestUIBoundary(unittest.TestCase):
    """Tests for Track 4: generated-ui vs dialogs boundary."""

    def test_ui_readme_exists(self):
        readme = ROOT / "ui" / "README.md"
        self.assertTrue(readme.exists(), "ui/README.md should exist")
        content = readme.read_text(encoding="utf-8")
        self.assertIn("pyuic6", content)
        self.assertIn("do not edit", content.lower())

    def test_generated_ui_files_have_warning(self):
        ui_dir = ROOT / "ui"
        for py_file in sorted(ui_dir.glob("*.py")):
            content = py_file.read_text(encoding="utf-8")
            if content.strip() == "":
                continue
            self.assertIn(
                "generated",
                content[:300].lower(),
                f"{py_file.name} missing generated-file header",
            )

    def test_dialogs_import_from_ui(self):
        """Each dialog wrapper should import its generated UI base class."""
        dialogs_dir = ROOT / "dialogs"
        skip = {"__init__.py", "sf_spatial_filter_dialog.py"}
        for py_file in sorted(dialogs_dir.glob("*.py")):
            if py_file.name in skip:
                continue
            content = py_file.read_text(encoding="utf-8")
            has_ui_import = "from ..ui." in content
            self.assertTrue(
                has_ui_import,
                f"{py_file.name} should import from ..ui.*",
            )

    def test_no_raw_pyqt_imports(self):
        """All plugin code should use qgis.PyQt, not raw PyQt5/PyQt6 imports."""
        for py_file in sorted(ROOT.rglob("*.py")):
            rel = py_file.relative_to(ROOT)
            if str(rel).startswith(("scripts", "test", "zip_build")):
                continue
            content = py_file.read_text(encoding="utf-8")
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                self.assertNotRegex(
                    stripped,
                    r"^(from|import)\s+PyQt[56]",
                    f"{rel} uses raw PyQt import: {stripped}",
                )


class TestStartupReliability(unittest.TestCase):
    """Tests for Track 2: guarded startup and dependency diagnostics."""

    def test_init_has_stub_plugin(self):
        content = (ROOT / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("class _StubPlugin", content)
        self.assertIn("def initGui(self)", content)
        self.assertIn("def unload(self)", content)

    def test_init_checks_missing_deps(self):
        content = (ROOT / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("missing = []", content)
        self.assertIn("check_package_installed", content)
        self.assertIn("QgsMessageLog.logMessage(", content)
        self.assertIn("return _StubPlugin()", content)

    def test_init_catches_import_errors(self):
        """classFactory must catch ImportError during plugin load and return stub."""
        content = (ROOT / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("except ImportError as imp_err:", content)
        self.assertIn("cryptography", content)
        self.assertIn("ExtensionOID", content)

    def test_check_install_package_returns_bool(self):
        content = (ROOT / "helpers" / "utils.py").read_text(encoding="utf-8")
        self.assertIn("def check_install_package(package_name) -> bool:", content)
        self.assertIn("def check_install_snowflake_connector_package() -> bool:", content)

    def test_check_install_package_delegates_to_check_package_installed(self):
        content = (ROOT / "helpers" / "utils.py").read_text(encoding="utf-8")
        idx_func = content.index("def check_install_package(")
        idx_next = content.index("\ndef ", idx_func + 1)
        func_body = content[idx_func:idx_next]
        self.assertIn("return check_package_installed(package_name)", func_body)
        self.assertNotIn("subprocess", func_body)
        self.assertNotIn("pip._internal", func_body)


class TestEditabilityCapabilities(unittest.TestCase):
    """Tests for GeoJSON editability / provider capability gating."""

    def _get_provider_content(self):
        return (ROOT / "providers" / "sf_vector_data_provider.py").read_text(
            encoding="utf-8"
        )

    def test_context_information_sets_table_name(self):
        """__init__ must add table_name to _context_information when _table_name is set."""
        content = self._get_provider_content()
        self.assertIn("if self._table_name:", content)
        self.assertNotIn(
            'if "table_name" in self._context_information:',
            content,
            "Dead conditional should be replaced with 'if self._table_name:'",
        )

    def test_capabilities_uses_geo_column_type_for_h3(self):
        """H3 read-only gate must check _geo_column_type, not _geometry_type == 'H3'."""
        content = self._get_provider_content()
        self.assertNotIn(
            '_geometry_type == "H3"',
            content,
            "capabilities() should not compare _geometry_type to 'H3'",
        )
        self.assertIn(
            '_geo_column_type not in ("GEOGRAPHY", "GEOMETRY")',
            content,
        )

    def test_capabilities_editable_for_geography_with_pk(self):
        """Verify capabilities logic allows editing for GEOGRAPHY/GEOMETRY with PK."""
        content = self._get_provider_content()
        idx = content.index("def capabilities(self)")
        next_def = content.index("\n    def ", idx + 1)
        body = content[idx:next_def]
        self.assertIn('self._primary_key == ""', body)
        self.assertIn("self._sql_query is not None", body)
        self.assertIn("AddFeatures", body)
        self.assertIn("ChangeGeometries", body)

    def test_change_geometry_values_propagates_failure(self):
        """changeGeometryValues must propagate update_table_feature failure."""
        content = self._get_provider_content()
        idx = content.index("def changeGeometryValues(")
        next_def = content.index("\n    def ", idx + 1)
        body = content[idx:next_def]
        self.assertIn("if not update_table_feature(context):", body)
        self.assertIn("all_ok = False", body)
        self.assertIn("return all_ok", body)

    def test_update_table_feature_logs_on_failure(self):
        """update_table_feature must log to QgsMessageLog on exception."""
        content = (ROOT / "helpers" / "data_base.py").read_text(encoding="utf-8")
        idx = content.index("def update_table_feature(")
        body = content[idx:]
        self.assertIn("QgsMessageLog.logMessage(", body)
        self.assertIn("update_table_feature failed", body)

    def _decode_uri(self, uri):
        """Replicates the decodeUri regex from helpers/utils.py for CI testing."""
        import re
        supported_keys = [
            "connection_name", "sql_query", "schema_name", "table_name",
            "srid", "geom_column", "geometry_type", "geo_column_type",
            "primary_key",
        ]
        matches = re.findall(
            f"({'|'.join(supported_keys)})=(.*?) *?(?={'|'.join(supported_keys)}=|$)",
            uri, flags=re.DOTALL,
        )
        return {key: value for key, value in matches}

    def test_uri_parsing_primary_key_roundtrip(self):
        """Verify decodeUri extracts primary_key correctly from browser-style URI."""
        uri = (
            "connection_name=myconn sql_query= "
            "schema_name=PUBLIC "
            "table_name=MYTABLE srid=4326 "
            "geom_column=GEOM "
            "geometry_type=Polygon "
            "geo_column_type=GEOGRAPHY "
            "primary_key=ID"
        )
        params = self._decode_uri(uri)
        self.assertEqual(params.get("primary_key"), "ID")
        self.assertEqual(params.get("sql_query"), "")

    def test_uri_parsing_empty_primary_key(self):
        """Verify decodeUri returns empty primary_key when none selected."""
        uri = (
            "connection_name=myconn sql_query= "
            "schema_name=PUBLIC "
            "table_name=MYTABLE srid=4326 "
            "geom_column=GEOM "
            "geometry_type=Polygon "
            "geo_column_type=GEOGRAPHY "
            "primary_key="
        )
        params = self._decode_uri(uri)
        self.assertEqual(params.get("primary_key"), "")


class TestUpdateNotification(unittest.TestCase):
    """Tests for #92: plugin update notification."""

    def test_plugin_has_update_check(self):
        content = (ROOT / "qgis_snowflake_connector.py").read_text(encoding="utf-8")
        self.assertIn("_check_for_updates", content)
        self.assertIn("releases/latest", content)
        self.assertIn("threading.Thread", content)

    def test_update_check_uses_metadata_version(self):
        content = (ROOT / "qgis_snowflake_connector.py").read_text(encoding="utf-8")
        self.assertIn("metadata.txt", content)
        self.assertIn("local_version", content)


class TestKeyPairAuth(unittest.TestCase):
    """Tests for #103: key pair authentication support."""

    def test_connection_dialog_has_key_pair_option(self):
        content = (ROOT / "dialogs" / "sf_connection_string_dialog.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"Key Pair"', content)
        self.assertIn("_txtKeyFile", content)
        self.assertIn("_txtKeyPassphrase", content)
        self.assertIn("_browse_key_file", content)

    def test_connection_manager_handles_key_pair(self):
        content = (ROOT / "managers" / "sf_connection_manager.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"Key Pair"', content)
        self.assertIn("private_key_file", content)
        self.assertIn("private_key_file_pwd", content)

    def test_settings_persist_key_pair_fields(self):
        content = (ROOT / "helpers" / "utils.py").read_text(encoding="utf-8")
        self.assertIn('"private_key_file"', content)
        self.assertIn('"key_passphrase"', content)


class TestH3TextNormalization(unittest.TestCase):
    """Tests that H3 cells are normalized to TEXT (hex string) internally."""

    def _get_iterator_content(self):
        return (ROOT / "providers" / "sf_feature_iterator.py").read_text(
            encoding="utf-8"
        )

    def _get_algorithm_content(self):
        return (ROOT / "qgis_snowflake_connector_algorithm.py").read_text(
            encoding="utf-8"
        )

    def test_no_python_h3_dependency(self):
        """Python h3 package must not be imported."""
        content = self._get_iterator_content()
        self.assertNotIn("import h3", content)

    def test_boundary_computed_server_side(self):
        """H3 boundary conversion uses Snowflake H3_CELL_TO_BOUNDARY."""
        content = self._get_iterator_content()
        self.assertIn("H3_CELL_TO_BOUNDARY", content)

    def test_number_h3_normalized_to_string(self):
        """NUMBER H3 columns are normalized to TEXT via H3_INT_TO_STRING."""
        content = self._get_iterator_content()
        self.assertIn("H3_INT_TO_STRING", content)

    def test_attribute_skip_preserves_h3(self):
        """Attribute skip condition allows H3 values through."""
        content = self._get_iterator_content()
        self.assertIn('not in ("NUMBER", "TEXT")', content)

    def test_sql_query_task_detects_h3_text_vs_number(self):
        """SQL query task distinguishes TEXT vs NUMBER H3 columns."""
        content = (ROOT / "tasks" / "sf_convert_sql_query_to_layer_task.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"TEXT"', content)
        self.assertIn('"NUMBER"', content)
        self.assertIn("h3_sf_col_type", content)


class TestPrimaryKeyValidation(unittest.TestCase):
    """Tests that primary key selection validates for duplicate values."""

    def _get_utils_content(self):
        return (ROOT / "helpers" / "utils.py").read_text(encoding="utf-8")

    def _get_database_content(self):
        return (ROOT / "helpers" / "data_base.py").read_text(encoding="utf-8")

    def test_check_column_has_duplicates_exists(self):
        """data_base.py must have a check_column_has_duplicates function."""
        content = self._get_database_content()
        self.assertIn("def check_column_has_duplicates(", content)

    def test_check_column_has_duplicates_uses_count_distinct(self):
        """The duplicate check must compare COUNT(*) vs COUNT(DISTINCT col)."""
        content = self._get_database_content()
        idx = content.index("def check_column_has_duplicates(")
        next_def = content.index("\ndef ", idx + 1)
        body = content[idx:next_def]
        self.assertIn("COUNT(*)", body)
        self.assertIn("COUNT(DISTINCT", body)
        self.assertIn("quote_identifier(column_name)", body)

    def test_prompt_calls_duplicate_check(self):
        """prompt_and_get_primary_key must call check_column_has_duplicates."""
        content = self._get_utils_content()
        idx = content.index("def prompt_and_get_primary_key(")
        next_def = content.index("\ndef ", idx + 1) if "\ndef " in content[idx + 1:] else len(content)
        body = content[idx:next_def]
        self.assertIn("check_column_has_duplicates", body)

    def test_prompt_warns_on_duplicates(self):
        """prompt_and_get_primary_key must show a warning when duplicates exist."""
        content = self._get_utils_content()
        self.assertIn("Duplicate Values Detected", content)


class TestEditingOperations(unittest.TestCase):
    """Tests that all declared editing capabilities have implementations."""

    def _get_provider_content(self):
        return (ROOT / "providers" / "sf_vector_data_provider.py").read_text(
            encoding="utf-8"
        )

    def _get_database_content(self):
        return (ROOT / "helpers" / "data_base.py").read_text(encoding="utf-8")

    def test_change_attribute_values_implemented(self):
        """changeAttributeValues must be implemented in the provider."""
        content = self._get_provider_content()
        self.assertIn("def changeAttributeValues(self", content)

    def test_add_features_implemented(self):
        """addFeatures must be implemented in the provider."""
        content = self._get_provider_content()
        self.assertIn("def addFeatures(self", content)

    def test_delete_features_implemented(self):
        """deleteFeatures must be implemented in the provider."""
        content = self._get_provider_content()
        self.assertIn("def deleteFeatures(self", content)

    def test_add_attributes_implemented(self):
        """addAttributes must be implemented with ALTER TABLE ADD COLUMN."""
        content = self._get_provider_content()
        self.assertIn("def addAttributes(self", content)
        db_content = self._get_database_content()
        self.assertIn("def alter_table_add_columns(", db_content)
        self.assertIn("ALTER TABLE", db_content)
        self.assertIn("ADD COLUMN", db_content)

    def test_delete_attributes_implemented(self):
        """deleteAttributes must be implemented with ALTER TABLE DROP COLUMN."""
        content = self._get_provider_content()
        self.assertIn("def deleteAttributes(self", content)
        db_content = self._get_database_content()
        self.assertIn("def alter_table_drop_columns(", db_content)
        self.assertIn("DROP COLUMN", db_content)

    def _get_func_body(self, content, func_name):
        idx = content.index(f"def {func_name}(")
        next_def = content.find("\ndef ", idx + 1)
        return content[idx:next_def] if next_def != -1 else content[idx:]

    def test_update_table_attributes_helper_exists(self):
        """data_base.py must have update_table_attributes helper."""
        content = self._get_database_content()
        body = self._get_func_body(content, "update_table_attributes")
        self.assertIn("UPDATE", body)
        self.assertIn("SET", body)
        self.assertIn("WHERE", body)

    def test_insert_table_feature_helper_exists(self):
        """data_base.py must have insert_table_feature helper."""
        content = self._get_database_content()
        body = self._get_func_body(content, "insert_table_feature")
        self.assertIn("INSERT INTO", body)
        self.assertIn("VALUES", body)

    def test_delete_table_features_helper_exists(self):
        """data_base.py must have delete_table_features helper."""
        content = self._get_database_content()
        body = self._get_func_body(content, "delete_table_features")
        self.assertIn("DELETE FROM", body)
        self.assertIn("IN (", body)

    def test_provider_imports_all_helpers(self):
        """Provider must import all editing helpers."""
        content = self._get_provider_content()
        for helper in [
            "update_table_attributes",
            "insert_table_feature",
            "delete_table_features",
            "alter_table_add_columns",
            "alter_table_drop_columns",
        ]:
            self.assertIn(helper, content)

    def test_context_information_includes_database_name(self):
        """_context_information must include database_name for FQ table refs."""
        content = self._get_provider_content()
        self.assertIn('database_name', content)
        self.assertIn('_auth_information', content)

    def test_qgis_to_snowflake_type_mapping(self):
        """Provider must have _QGIS_TO_SF_TYPE mapping for addAttributes."""
        content = self._get_provider_content()
        self.assertIn("_QGIS_TO_SF_TYPE", content)
        for sf_type in ["TEXT", "INTEGER", "DOUBLE", "DATE", "BOOLEAN"]:
            self.assertIn(f'"{sf_type}"', content)

    def test_all_helpers_log_errors(self):
        """All DML helpers must log errors via QgsMessageLog."""
        content = self._get_database_content()
        for func in [
            "update_table_attributes",
            "insert_table_feature",
            "delete_table_features",
            "alter_table_add_columns",
            "alter_table_drop_columns",
        ]:
            idx = content.index(f"def {func}(")
            next_def_pos = content.find("\ndef ", idx + 1)
            body = content[idx:next_def_pos] if next_def_pos != -1 else content[idx:]
            self.assertIn("QgsMessageLog.logMessage", body,
                          f"{func} must log errors")

    def test_editing_methods_call_reload_or_update_cache(self):
        """Editing methods must call reloadData() to refresh the cache."""
        content = self._get_provider_content()
        for method in ["addFeatures", "deleteFeatures", "changeAttributeValues"]:
            idx = content.index(f"def {method}(self")
            next_def = content.index("\n    def ", idx + 1)
            body = content[idx:next_def]
            self.assertIn("reloadData()", body,
                          f"{method} must call reloadData()")
        idx = content.index("def changeAttributeValues(self")
        next_def = content.index("\n    def ", idx + 1)
        body = content[idx:next_def]
        self.assertIn("update_table_attributes", body,
                      "changeAttributeValues must persist to Snowflake")

    def test_editing_methods_propagate_errors_via_push_error(self):
        """All editing methods must call pushError() to surface Snowflake errors."""
        content = self._get_provider_content()
        for method in [
            "changeAttributeValues", "addFeatures", "deleteFeatures",
            "addAttributes", "deleteAttributes",
        ]:
            idx = content.index(f"def {method}(self")
            next_def = content.find("\n    def ", idx + 1)
            body = content[idx:next_def] if next_def != -1 else content[idx:]
            self.assertIn("self.pushError(", body,
                          f"{method} must call pushError() to propagate Snowflake errors")


    def test_reload_data_preserves_fields(self):
        """reloadData() must NOT reset _fields to avoid column order scrambling."""
        content = self._get_provider_content()
        idx = content.index("def reloadData(self)")
        next_def = content.index("\n    def ", idx + 1)
        body = content[idx:next_def]
        self.assertNotIn("self._fields = None", body,
                         "reloadData() must not reset _fields")

    def test_default_value_implemented_for_primary_key(self):
        """Provider must implement defaultValue() for auto-increment PK."""
        content = self._get_provider_content()
        self.assertIn("def defaultValue(self", content)
        idx = content.index("def defaultValue(self")
        next_def = content.index("\n    def ", idx + 1)
        body = content[idx:next_def]
        self.assertIn("_primary_key", body,
                      "defaultValue must check primary key column")
        self.assertIn("get_next_primary_key_value", body,
                      "defaultValue must query next PK value from Snowflake")

    def test_get_next_primary_key_value_helper_exists(self):
        """data_base.py must have get_next_primary_key_value helper."""
        content = self._get_database_content()
        self.assertIn("def get_next_primary_key_value(", content)
        idx = content.index("def get_next_primary_key_value(")
        next_def = content.find("\ndef ", idx + 1)
        body = content[idx:next_def] if next_def != -1 else content[idx:]
        self.assertIn("MAX(", body)
        self.assertIn("COALESCE", body)

    def test_reload_data_emits_data_changed(self):
        """reloadData() must emit dataChanged so edits surface without reopening."""
        content = self._get_provider_content()
        idx = content.index("def reloadData(self)")
        next_def = content.index("\n    def ", idx + 1)
        body = content[idx:next_def]
        self.assertIn("self.dataChanged.emit(", body,
                      "reloadData must emit dataChanged to refresh QGIS caches")

    def test_add_features_sets_feature_id(self):
        """addFeatures must stamp each inserted feature with its PK as fid."""
        content = self._get_provider_content()
        idx = content.index("def addFeatures(self")
        next_def = content.index("\n    def ", idx + 1)
        body = content[idx:next_def]
        self.assertIn("feat.setId(", body,
                      "addFeatures must assign fid from the PK value on success")

    def test_default_value_clause_implemented_for_primary_key(self):
        """Provider must implement defaultValueClause() to advertise the auto-ID default."""
        content = self._get_provider_content()
        self.assertIn("def defaultValueClause(self", content)
        idx = content.index("def defaultValueClause(self")
        next_def = content.index("\n    def ", idx + 1)
        body = content[idx:next_def]
        self.assertIn("_primary_key", body,
                      "defaultValueClause must only advertise for the PK column")


class TestGitHubIssuesFixes(unittest.TestCase):
    """Tests for remaining GitHub issues fixes."""

    def test_no_subprocess_or_pip_in_install_path_issue_114(self):
        """check_install_package must NOT invoke subprocess or pip (issue #114).

        Auto-installing via pip on the UI thread froze QGIS on macOS because
        the resolved 'python3' was actually a QGIS launcher stub.
        """
        content = (ROOT / "helpers" / "utils.py").read_text(encoding="utf-8")
        self.assertNotIn("def _safe_pip_call(", content)
        self.assertNotIn("def _in_process_pip(", content)
        self.assertNotIn("def get_python_executable_path(", content)
        self.assertNotIn("subprocess", content)
        self.assertNotIn("pip._internal", content)

        init_content = (ROOT / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("_StubPlugin", init_content)
        self.assertIn("python3 -m pip install snowflake-connector-python", init_content)

    def test_sql_branch_qgsfield_type_default_fixed(self):
        """SQL-query branch QgsField construction should use correct default."""
        content = (ROOT / "providers" / "sf_vector_data_provider.py").read_text(encoding="utf-8")
        # The buggy pattern was: SNOWFLAKE_METADATA_TYPE_CODE_DICT[2]["qvariant_type"] as default
        # Fixed pattern: SNOWFLAKE_METADATA_TYPE_CODE_DICT[2] as default (the full dict)
        # Check that the fixed pattern exists
        self.assertIn("SNOWFLAKE_METADATA_TYPE_CODE_DICT.get", content)
        # Ensure we're not using the buggy nested default
        buggy_pattern = 'SNOWFLAKE_METADATA_TYPE_CODE_DICT[2]["qvariant_type"]'
        self.assertNotIn(buggy_pattern, content,
                         "SQL branch should not use buggy nested default for unknown type codes")

    def test_non_geo_tables_support_added(self):
        """Browser should support showing non-geometry tables."""
        content = (ROOT / "entities" / "sf_data_item.py").read_text(encoding="utf-8")
        self.assertIn("get_table_iterator", content)
        self.assertIn("table_no_geom", content)
        self.assertIn("Tables (no geometry)", content)

    def test_empty_schema_feedback_added(self):
        """Schema with no tables should show QgsErrorItem feedback."""
        content = (ROOT / "entities" / "sf_data_item.py").read_text(encoding="utf-8")
        self.assertIn("No accessible tables found", content)
        self.assertIn("QgsErrorItem", content)


class TestOpenIssueFixes(unittest.TestCase):
    """Fixes for the open tracker issues #120, #119 and #118."""

    def test_qgsfield_helper_is_version_compatible(self):
        """#120: QgsField must be built through a helper that falls back to
        QVariant.Type on QGIS < 3.38 (the QMetaType.Type constructor is only
        available from 3.38)."""
        content = (ROOT / "helpers" / "mappings.py").read_text(encoding="utf-8")
        self.assertIn("def create_qgs_field(", content)
        self.assertIn("QGIS_VERSION_INT", content)
        self.assertIn("33800", content)
        self.assertIn("QVariant.Type(int(metatype))", content)

    def test_qgsfield_construction_sites_use_helper(self):
        """#120: every QgsField construction that takes a QMetaType.Type must
        route through create_qgs_field."""
        for rel in [
            ("providers", "sf_data_source_provider.py"),
            ("providers", "sf_vector_data_provider.py"),
            ("processing", "import_from_snowflake.py"),
            ("helpers", "layer_creation.py"),
        ]:
            content = (ROOT.joinpath(*rel)).read_text(encoding="utf-8")
            self.assertIn(
                "create_qgs_field(", content,
                f"{'/'.join(rel)} must build fields via create_qgs_field",
            )

    def test_feature_iterator_initializes_expression_unconditionally(self):
        """#119: self._expression must be set before the features-cached guard
        so nextFeatureFilterExpression never hits an unset attribute."""
        content = (ROOT / "providers" / "sf_feature_iterator.py").read_text(
            encoding="utf-8"
        )
        init_expr = content.index('self._expression = ""')
        guard = content.index("if not self._provider._features_loaded:")
        self.assertLess(
            init_expr, guard,
            "self._expression must be initialized before the "
            "_features_loaded guard",
        )

    def test_data_item_handles_table_group_and_no_geom(self):
        """#118: expanding 'Tables (no geometry)' must not fall through to
        _get_query_metadata with an unhandled item_type."""
        content = (ROOT / "entities" / "sf_data_item.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("def create_table_group_item(", content)
        self.assertIn('elif self.item_type == "table_group":', content)
        self.assertIn('if self.item_type in ("field", "table_no_geom"):', content)
        # Children are built lazily from a stashed list, not pre-added.
        self.assertIn("group_item.non_geo_tables = sorted(non_geo_tables)", content)
        self.assertNotIn("group_item.addChildItem(", content)


class TestSpatialFilterPushdownGuard(unittest.TestCase):
    """Regression: the GEOGRAPHY / H3 spatial-filter pushdown must be skipped
    when the filter rect is outside the WGS84 lon/lat range, otherwise
    Snowflake rejects the ST_GEOGRAPHYFROMWKT polygon with
    ``GeoJSON::Polygon::Loop: Invalid Lng/Lat pair``. See issue exposed by
    commit ac882d5 (spatial filter pushdown column-type fix).
    """

    def _iterator_content(self):
        return (ROOT / "providers" / "sf_feature_iterator.py").read_text(
            encoding="utf-8"
        )

    def test_helper_defined(self):
        content = self._iterator_content()
        self.assertIn("def _rect_is_valid_lonlat(", content)

    def test_geography_branch_guarded(self):
        """GEOGRAPHY branch must call _rect_is_valid_lonlat before emitting
        ST_GEOGRAPHYFROMWKT."""
        content = self._iterator_content()
        idx = content.index('_geo_column_type == "GEOGRAPHY"')
        next_branch = content.index(
            '_geo_column_type in ["NUMBER", "TEXT"]', idx
        )
        branch_body = content[idx:next_branch]
        self.assertIn("_rect_is_valid_lonlat(filter_rect)", branch_body)
        self.assertIn("ST_GEOGRAPHYFROMWKT", branch_body)
        self.assertIn("Skipping spatial filter pushdown", branch_body)

    def test_h3_branch_guarded(self):
        """H3 (NUMBER / TEXT) branch must also be guarded."""
        content = self._iterator_content()
        idx = content.index('_geo_column_type in ["NUMBER", "TEXT"]')
        next_block = content.index(
            'if filter_geom_clause != ""', idx
        )
        branch_body = content[idx:next_block]
        self.assertIn("_rect_is_valid_lonlat(filter_rect)", branch_body)
        self.assertIn("H3_CELL_TO_BOUNDARY", branch_body)

    def test_geometry_branch_unchanged(self):
        """GEOMETRY branch must not be guarded (ST_GEOMETRYFROMWKT accepts
        any coordinate range)."""
        content = self._iterator_content()
        idx = content.index('_geo_column_type == "GEOMETRY"')
        next_branch = content.index(
            '_geo_column_type == "GEOGRAPHY"', idx
        )
        branch_body = content[idx:next_branch]
        self.assertIn("ST_GEOMETRYFROMWKT", branch_body)
        self.assertNotIn("_rect_is_valid_lonlat", branch_body)

    def test_rect_is_valid_lonlat_rejects_out_of_range(self):
        """Unit-test the helper directly against the exact rect from the
        user-reported failure (coords like 2821.43, 861.237)."""
        class _FakeRect:
            def __init__(self, xmin, ymin, xmax, ymax):
                self._xmin, self._ymin = xmin, ymin
                self._xmax, self._ymax = xmax, ymax

            def xMinimum(self): return self._xmin
            def yMinimum(self): return self._ymin
            def xMaximum(self): return self._xmax
            def yMaximum(self): return self._ymax

        import importlib.util
        import sys
        import types

        qgis_core = types.ModuleType("qgis.core")
        for name in [
            "QgsAbstractFeatureIterator", "QgsCoordinateTransform",
            "QgsCsException", "QgsFeature", "QgsFeatureRequest",
            "QgsGeometry", "QgsMessageLog", "Qgis",
        ]:
            setattr(qgis_core, name, type(name, (), {}))
        qgis_pkg = types.ModuleType("qgis")
        qgis_pkg.core = qgis_core
        qgis_pyqt = types.ModuleType("qgis.PyQt")
        qgis_pyqt_qtcore = types.ModuleType("qgis.PyQt.QtCore")
        for name in ("QDate", "QDateTime", "QMetaType", "QTime"):
            setattr(qgis_pyqt_qtcore, name, type(name, (), {}))
        qgis_pyqt.QtCore = qgis_pyqt_qtcore
        sys.modules.setdefault("qgis", qgis_pkg)
        sys.modules.setdefault("qgis.core", qgis_core)
        sys.modules.setdefault("qgis.PyQt", qgis_pyqt)
        sys.modules.setdefault("qgis.PyQt.QtCore", qgis_pyqt_qtcore)

        plugin_pkg = types.ModuleType("qgis_snowflake_connector")
        plugin_pkg.__path__ = [str(ROOT)]
        helpers_pkg = types.ModuleType("qgis_snowflake_connector.helpers")
        helpers_pkg.__path__ = [str(ROOT / "helpers")]
        helpers_limits = types.ModuleType(
            "qgis_snowflake_connector.helpers.limits"
        )
        helpers_limits.limit_size_for_type = lambda t: 0
        helpers_sql = types.ModuleType(
            "qgis_snowflake_connector.helpers.sql"
        )
        helpers_sql.quote_identifier = lambda n: n
        helpers_sql.quote_literal = lambda v: "'" + str(v).replace("'", "''") + "'"
        helpers_expression_compiler = types.ModuleType(
            "qgis_snowflake_connector.helpers.expression_compiler"
        )
        helpers_expression_compiler.compile_expression_to_sql = (
            lambda expr, fields: None
        )
        helpers_mappings = types.ModuleType(
            "qgis_snowflake_connector.helpers.mappings"
        )
        helpers_mappings.mapping_multi_single_to_geometry_type = {}
        providers_pkg = types.ModuleType(
            "qgis_snowflake_connector.providers"
        )
        providers_pkg.__path__ = [str(ROOT / "providers")]
        sf_feature_source = types.ModuleType(
            "qgis_snowflake_connector.providers.sf_feature_source"
        )
        sf_feature_source.SFFeatureSource = type("SFFeatureSource", (), {})
        managers_pkg = types.ModuleType(
            "qgis_snowflake_connector.managers"
        )
        managers_pkg.__path__ = [str(ROOT / "managers")]
        sf_connection_manager = types.ModuleType(
            "qgis_snowflake_connector.managers.sf_connection_manager"
        )
        sf_connection_manager.build_op_tag = lambda *a, **k: ""
        for mod in (
            plugin_pkg, helpers_pkg, helpers_limits, helpers_sql,
            helpers_expression_compiler,
            helpers_mappings, providers_pkg, sf_feature_source,
            managers_pkg, sf_connection_manager,
        ):
            sys.modules.setdefault(mod.__name__, mod)

        spec = importlib.util.spec_from_file_location(
            "qgis_snowflake_connector.providers.sf_feature_iterator",
            ROOT / "providers" / "sf_feature_iterator.py",
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        rect_bad = _FakeRect(-5392.42, -2469.11, 2821.43, 861.237)
        self.assertFalse(module._rect_is_valid_lonlat(rect_bad))
        rect_good = _FakeRect(-10.0, -10.0, 10.0, 10.0)
        self.assertTrue(module._rect_is_valid_lonlat(rect_good))
        rect_world = _FakeRect(-180.0, -90.0, 180.0, 90.0)
        self.assertTrue(module._rect_is_valid_lonlat(rect_world))
        rect_over_lon = _FakeRect(-10.0, -10.0, 180.001, 10.0)
        self.assertFalse(module._rect_is_valid_lonlat(rect_over_lon))
        rect_over_lat = _FakeRect(-10.0, -90.001, 10.0, 10.0)
        self.assertFalse(module._rect_is_valid_lonlat(rect_over_lat))


class TestQualityBaseline(unittest.TestCase):
    """Tests for Track 5: CONTRIBUTING and CI baseline."""

    def test_ci_workflow_exists(self):
        path = ROOT / ".github" / "workflows" / "ci.yml"
        self.assertTrue(path.exists(), ".github/workflows/ci.yml should exist")
        content = path.read_text(encoding="utf-8")
        self.assertIn("flake8", content)
        self.assertIn("py_compile", content)
        self.assertIn("test_issue_regressions", content)

    def test_tests_are_split_by_track(self):
        """Test file should have separate classes for each improvement track."""
        content = (ROOT / "test" / "test_issue_regressions.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("class TestIssueRegressions", content)
        self.assertIn("class TestSQLSafety", content)
        self.assertIn("class TestStartupReliability", content)
        self.assertIn("class TestProviderLifecycle", content)
        self.assertIn("class TestUIBoundary", content)
        self.assertIn("class TestQualityBaseline", content)


class TestFeatureCachePoisoning(unittest.TestCase):
    """Regression: a per-request-filtered query (spatial rect, fid, or pushed-
    down expression) must NOT populate the provider-shared feature cache or
    mark the layer fully loaded. Otherwise the first filtered render caps the
    layer to that subset for every later full-extent request.
    """

    def _iterator_content(self):
        return (ROOT / "providers" / "sf_feature_iterator.py").read_text(
            encoding="utf-8"
        )

    def test_should_cache_features_flag_defined(self):
        content = self._iterator_content()
        self.assertIn("self._should_cache_features", content)
        self.assertIn("self._should_cache_features = (", content)

    def test_cache_gate_condition(self):
        """The gate must fail closed for any per-request filter."""
        content = self._iterator_content()
        idx = content.index("self._should_cache_features = (")
        block = content[idx:idx + 300]
        self.assertIn(
            'not getattr(self._provider, "_load_all_rows", False)', block
        )
        self.assertIn("and feature_id_list is None", block)
        self.assertIn('and self._expression == ""', block)
        self.assertIn('and filter_geom_clause == ""', block)

    def test_features_loaded_gated_on_flag(self):
        content = self._iterator_content()
        self.assertIn(
            "if self._should_cache_features:\n"
            "                        self._provider._features_loaded = True",
            content,
        )
        # The old load_all_rows-only guard must no longer wrap this write.
        self.assertNotIn(
            'if not getattr(self._provider, "_load_all_rows", False):\n'
            "                        self._provider._features_loaded = True",
            content,
        )

    def test_features_append_gated_on_flag(self):
        content = self._iterator_content()
        self.assertIn(
            "if self._should_cache_features:\n"
            "                    self._provider._features.append(QgsFeature(f))",
            content,
        )
        self.assertNotIn(
            'if not getattr(self._provider, "_load_all_rows", False):\n'
            "                    self._provider._features.append(QgsFeature(f))",
            content,
        )


class TestGeometryTypeCountFilter(unittest.TestCase):
    """Regression: featureCount() and extent() must restrict to the layer's
    geometry type (plus its single/multi partner) so a geometry column that
    mixes families does not over-count or compute the wrong extent.
    """

    def _provider_content(self):
        return (ROOT / "providers" / "sf_vector_data_provider.py").read_text(
            encoding="utf-8"
        )

    def test_geometry_type_filter_helper_exists(self):
        content = self._provider_content()
        self.assertIn("def _geometry_type_filter(self)", content)
        idx = content.index("def _geometry_type_filter(self)")
        next_def = content.index("\n    def ", idx + 1)
        body = content[idx:next_def]
        self.assertIn("mapping_multi_single_to_geometry_type", body)
        self.assertIn("quote_identifier(self._column_geom)", body)
        self.assertIn("quote_literal(", body)
        self.assertIn("ST_ASGEOJSON(", body)
        self.assertIn("IN (", body)

    def test_helper_imported(self):
        content = self._provider_content()
        self.assertIn("mapping_multi_single_to_geometry_type", content)

    def test_feature_count_uses_geometry_type_filter(self):
        content = self._provider_content()
        # SFGeoVectorDataProvider.featureCount applies the geometry-type filter
        # (unless the single-geom fast path is active) and builds COUNT(*).
        self.assertIn("SELECT COUNT(*) FROM {self._from_clause}", content)
        self.assertIn("where_parts.append(self._geometry_type_filter())", content)

    def test_extent_uses_geometry_type_filter_not_ilike(self):
        content = self._provider_content()
        self.assertIn("{self._geometry_type_filter()}", content)
        # The old single-type ILIKE form must be gone.
        self.assertNotIn(":type ILIKE ", content)


class TestIntegerColumnMapping(unittest.TestCase):
    """Regression: NUMBER/DECIMAL columns with scale 0 (including primary keys)
    must map to an integer QMetaType, not Double (which renders 1.0)."""

    def _mappings(self):
        return (ROOT / "helpers" / "mappings.py").read_text(encoding="utf-8")

    def _provider(self):
        return (ROOT / "providers" / "sf_vector_data_provider.py").read_text(
            encoding="utf-8"
        )

    def test_map_numeric_type_helper_exists(self):
        content = self._mappings()
        self.assertIn("def map_numeric_type(", content)
        idx = content.index("def map_numeric_type(")
        body = content[idx:idx + 900]
        self.assertIn("QMetaType.Type.LongLong", body)
        self.assertIn("NUMBER", body)
        self.assertIn("DECIMAL", body)

    def test_table_branch_uses_scale_and_helper(self):
        content = self._provider()
        self.assertIn("map_numeric_type", content)
        # The information_schema query must fetch numeric_scale.
        self.assertIn("numeric_scale", content)
        self.assertIn("map_numeric_type(field_type, numeric_scale)", content)

    def test_sql_query_branch_detects_fixed_scale_zero(self):
        content = self._provider()
        # description scale is index 5; FIXED with scale 0 -> LongLong.
        self.assertIn("data[5]", content)
        self.assertIn('meta.get("name") == "FIXED"', content)
        self.assertIn("QMetaType.Type.LongLong", content)

    def test_longlong_roundtrips_in_addAttributes_map(self):
        content = self._provider()
        self.assertIn('QMetaType.Type.LongLong: "NUMBER"', content)


class TestSchemaQualifiedFromClause(unittest.TestCase):
    """Regression: the table-branch from_clause must be fully qualified so
    COUNT/extent/iteration do not depend on the session's current schema."""

    def _provider(self):
        return (ROOT / "providers" / "sf_vector_data_provider.py").read_text(
            encoding="utf-8"
        )

    def test_imports_qualified_helper(self):
        content = self._provider()
        self.assertIn("qualified_table_name", content)

    def test_table_branch_qualifies(self):
        content = self._provider()
        self.assertIn(
            "qualified_table_name(\n"
            "                    database_name, self._schema_name, self._table_name\n"
            "                )",
            content,
        )
        # Bare-name fallback is still present for the db/schema-unknown case.
        self.assertIn(
            "self._from_clause = quote_identifier(self._table_name)", content
        )


class TestSingleGeomCountFastPath(unittest.TestCase):
    """Regression: a single-geometry-family layer must skip the per-row
    ST_ASGEOJSON type predicate so featureCount() uses a metadata COUNT(*)."""

    def _provider(self):
        return (ROOT / "providers" / "sf_vector_data_provider.py").read_text(
            encoding="utf-8"
        )

    def test_uri_key_supported(self):
        utils = (ROOT / "helpers" / "utils.py").read_text(encoding="utf-8")
        self.assertIn('"single_geom_layer"', utils)

    def test_parse_uri_returns_flag(self):
        wrapper = (ROOT / "helpers" / "wrapper.py").read_text(encoding="utf-8")
        self.assertIn(
            'single_geom_layer = parsed_uri.get("single_geom_layer", "") == "1"',
            wrapper,
        )
        self.assertIn("single_geom_layer,", wrapper)

    def test_featurecount_and_extent_branch_on_flag(self):
        content = self._provider()
        self.assertEqual(content.count('getattr(self, "_single_geom_layer", False)'), 2)

    def test_tasks_set_flag_when_single_type(self):
        col = (ROOT / "tasks" / "sf_convert_column_to_layer_task.py").read_text(
            encoding="utf-8"
        )
        sql = (ROOT / "tasks" / "sf_convert_sql_query_to_layer_task.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("single_geom_layer=1", col)
        self.assertIn("single_geom_layer=1", sql)


class TestFeatureCountCacheSentinel(unittest.TestCase):
    """Regression: an empty layer (count 0) must not re-run COUNT every call."""

    def test_uses_is_none_sentinel(self):
        content = (ROOT / "providers" / "sf_vector_data_provider.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("if self._feature_count is None:", content)
        # The old truthiness check must be gone from the count getters.
        self.assertNotIn("if not self._feature_count:", content)


class TestEditCacheGuards(unittest.TestCase):
    """Regression: edit methods must not IndexError when the fid-indexed
    feature cache is empty (e.g. right after a commit's reloadData())."""

    def _provider(self):
        return (ROOT / "providers" / "sf_vector_data_provider.py").read_text(
            encoding="utf-8"
        )

    def test_ensure_features_loaded_helper_exists(self):
        content = self._provider()
        self.assertIn("def _ensure_features_loaded(self)", content)

    def test_edit_methods_call_ensure_and_guard(self):
        content = self._provider()
        # All three edit methods repopulate the cache before indexing it.
        self.assertEqual(content.count("self._ensure_features_loaded()"), 3)
        # changeGeometryValues bounds-checks the key it indexes.
        self.assertIn("if f_key < 0 or f_key >= len(self._features):", content)
        # deleteFeatures bounds-checks each fid too.
        self.assertEqual(
            content.count("if fid < 0 or fid >= len(self._features):"), 2
        )


class TestProcessingConnectionReuse(unittest.TestCase):
    """Regression: processing algorithms must reuse an existing open connection.

    SFConnectionManager.connect() force-closes and rebuilds the shared session,
    which disrupts already-loaded layers and can freeze the UI thread. Every
    algorithm must guard the call with `get_connection(...) is None`.
    """

    def test_no_unguarded_connect_in_processing(self):
        processing_dir = ROOT / "processing"
        offenders = []
        for path in sorted(processing_dir.glob("*.py")):
            lines = path.read_text(encoding="utf-8").splitlines()
            for i, line in enumerate(lines):
                stripped = line.strip()
                if not stripped.startswith("mgr.connect("):
                    continue
                # The two preceding non-blank lines must contain the guard.
                window = "\n".join(lines[max(0, i - 3):i])
                if "get_connection(" not in window:
                    offenders.append(f"{path.name}:{i + 1}")
        self.assertEqual(
            offenders,
            [],
            f"Unguarded mgr.connect() in processing algorithms: {offenders}",
        )


class TestBufferTransformNotFused(unittest.TestCase):
    """Regression: the GEOGRAPHY buffer must not fuse ST_TRANSFORM with
    ST_BUFFER in one SQL expression.

    Snowflake's optimizer produces a pathological plan for
    ST_TRANSFORM(ST_BUFFER(...)) / ST_BUFFER(ST_TRANSFORM(...)) that never
    returns and freezes the QGIS UI. The algorithm must materialize each
    geometry operation into a separate (temporary) table so no single
    statement combines a transform with a buffer.
    """

    def _source(self):
        return (ROOT / "processing" / "buffer_table.py").read_text(encoding="utf-8")

    def test_no_transform_buffer_fusion(self):
        src = self._source()
        # Collapse whitespace so multi-line f-strings are matched too.
        flat = re.sub(r"\s+", "", src)
        self.assertNotIn("ST_TRANSFORM(ST_BUFFER", flat)
        self.assertNotIn("ST_BUFFER(ST_TRANSFORM", flat)

    def test_uses_temporary_materialization(self):
        src = self._source()
        self.assertIn("CREATE OR REPLACE TEMPORARY TABLE", src)


class TestStatementTimeoutSafetyNet(unittest.TestCase):
    """Regression: connections must set a bounded STATEMENT_TIMEOUT so a stuck
    query can never block the QGIS main thread indefinitely.
    """

    def test_statement_timeout_in_session_parameters(self):
        src = (
            ROOT / "managers" / "sf_connection_manager.py"
        ).read_text(encoding="utf-8")
        self.assertIn("STATEMENT_TIMEOUT_IN_SECONDS", src)


class TestImportDecimalCoercion(unittest.TestCase):
    """Regression: imported Snowflake NUMBER values arrive as Decimal, which
    the memory/OGR providers cannot store into a double field (the feature is
    silently rejected). The import loop must coerce Decimal to float.
    """

    def test_decimal_coerced_to_float(self):
        src = (
            ROOT / "processing" / "import_from_snowflake.py"
        ).read_text(encoding="utf-8")
        self.assertIn("Decimal", src)
        flat = re.sub(r"\s+", "", src)
        self.assertIn("isinstance(val,Decimal)", flat)
        self.assertIn("float(val)", flat)


if __name__ == "__main__":
    unittest.main()
