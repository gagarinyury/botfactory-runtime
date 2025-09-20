"""Unit tests for SQL builder and parameter handling"""
import pytest
import json
from unittest.mock import AsyncMock
from runtime.actions import ActionExecutor


class TestSQLParameterBuilder:
    """Test SQL parameter building functionality"""

    def setup_method(self):
        """Setup test fixtures"""
        self.mock_session = AsyncMock()
        self.executor = ActionExecutor(self.mock_session, "test-bot-123", 45678)

    def test_build_basic_parameters(self):
        """Test building basic bot_id and user_id parameters"""
        self.executor._set_action_type('sql_query')

        params = self.executor._build_safe_parameters()

        assert params["bot_id"] == "test-bot-123"
        assert params["user_id"] == 45678
        assert isinstance(params["user_id"], int)

    def test_build_parameters_with_string_variables(self):
        """Test parameter building with string context variables"""
        self.executor._set_action_type('sql_exec')
        self.executor.set_context_var("service", "massage")
        self.executor.set_context_var("user_name", "John Doe")

        params = self.executor._build_safe_parameters()

        assert params["bot_id"] == "test-bot-123"
        assert params["user_id"] == 45678
        assert params["service"] == "massage"
        assert params["user_name"] == "John Doe"

    def test_build_parameters_with_numeric_variables(self):
        """Test parameter building with numeric context variables"""
        self.executor._set_action_type('sql_query')
        self.executor.set_context_var("count", 5)
        self.executor.set_context_var("price", 99.99)
        self.executor.set_context_var("discount", 0.15)

        params = self.executor._build_safe_parameters()

        assert params["count"] == 5
        assert params["price"] == 99.99
        assert params["discount"] == 0.15

    def test_build_parameters_with_boolean_variables(self):
        """Test parameter building with boolean context variables"""
        self.executor._set_action_type('sql_exec')
        self.executor.set_context_var("is_active", True)
        self.executor.set_context_var("is_verified", False)

        params = self.executor._build_safe_parameters()

        assert params["is_active"] is True
        assert params["is_verified"] is False

    def test_build_parameters_with_none_values(self):
        """Test parameter building with None values"""
        self.executor._set_action_type('sql_query')
        self.executor.set_context_var("optional_field", None)
        self.executor.set_context_var("nullable_data", None)

        params = self.executor._build_safe_parameters()

        assert params["optional_field"] is None
        assert params["nullable_data"] is None

    def test_build_parameters_with_complex_types_serialized(self):
        """Test that complex types are JSON serialized"""
        self.executor._set_action_type('sql_exec')

        # Complex data structures
        list_data = ["item1", "item2", "item3"]
        dict_data = {"key": "value", "nested": {"inner": "data"}}

        self.executor.set_context_var("items", list_data)
        self.executor.set_context_var("metadata", dict_data)

        params = self.executor._build_safe_parameters()

        # Should be JSON serialized
        assert params["items"] == json.dumps(list_data)
        assert params["metadata"] == json.dumps(dict_data)

    def test_build_parameters_mixed_types(self):
        """Test parameter building with mixed variable types"""
        self.executor._set_action_type('sql_query')

        # Set various types
        self.executor.set_context_var("text", "hello")
        self.executor.set_context_var("number", 42)
        self.executor.set_context_var("decimal", 3.14)
        self.executor.set_context_var("flag", True)
        self.executor.set_context_var("empty", None)
        self.executor.set_context_var("data", {"complex": "object"})

        params = self.executor._build_safe_parameters()

        # Basic parameters
        assert params["bot_id"] == "test-bot-123"
        assert params["user_id"] == 45678

        # Variable parameters
        assert params["text"] == "hello"
        assert params["number"] == 42
        assert params["decimal"] == 3.14
        assert params["flag"] is True
        assert params["empty"] is None
        assert params["data"] == json.dumps({"complex": "object"})

    def test_build_parameters_invalid_action_type(self):
        """Test that invalid action types raise errors"""
        # Don't set action type
        with pytest.raises(ValueError, match="Invalid action type: unknown"):
            self.executor._build_safe_parameters()

        # Set invalid action type
        self.executor._set_action_type('invalid_action')
        with pytest.raises(ValueError, match="Invalid action type: invalid_action"):
            self.executor._build_safe_parameters()

    def test_build_parameters_valid_action_types(self):
        """Test that valid action types work correctly"""
        # Test sql_query
        self.executor._set_action_type('sql_query')
        params1 = self.executor._build_safe_parameters()
        assert "bot_id" in params1

        # Test sql_exec
        self.executor._set_action_type('sql_exec')
        params2 = self.executor._build_safe_parameters()
        assert "bot_id" in params2

    def test_user_id_type_conversion(self):
        """Test that user_id is properly converted to int"""
        # Test with string user_id
        executor_str = ActionExecutor(self.mock_session, "bot-id", "12345")
        executor_str._set_action_type('sql_query')

        params = executor_str._build_safe_parameters()
        assert params["user_id"] == 12345
        assert isinstance(params["user_id"], int)


class TestSQLSafetyValidation:
    """Test SQL safety validation functionality"""

    def setup_method(self):
        """Setup test fixtures"""
        self.mock_session = AsyncMock()
        self.executor = ActionExecutor(self.mock_session, "test-bot", 123)

    def test_validate_sql_query_statements(self):
        """Test validation of SELECT statements for sql_query actions"""
        self.executor._set_action_type('sql_query')

        # Valid SELECT statements
        valid_queries = [
            "SELECT * FROM users",
            "SELECT id, name FROM bookings WHERE bot_id = :bot_id",
            "select count(*) from stats",
            "  SELECT service, slot FROM bookings ORDER BY created_at  ",
        ]

        for sql in valid_queries:
            # Should not raise exception
            self.executor._validate_sql_safety(sql)

    def test_validate_sql_exec_statements(self):
        """Test validation of INSERT/DELETE statements for sql_exec actions"""
        self.executor._set_action_type('sql_exec')

        # Valid INSERT statements
        valid_inserts = [
            "INSERT INTO bookings (service, user_id) VALUES (:service, :user_id)",
            "insert into logs (message) values ('test')",
            "  INSERT INTO users (name) VALUES (:name)  ",
        ]

        for sql in valid_inserts:
            self.executor._validate_sql_safety(sql)

        # Valid DELETE statements
        valid_deletes = [
            "DELETE FROM bookings WHERE id = :id",
            "delete from old_data where created_at < now()",
            "  DELETE FROM temp_table  ",
        ]

        for sql in valid_deletes:
            self.executor._validate_sql_safety(sql)

    def test_validate_sql_query_rejects_non_select(self):
        """Test that sql_query actions reject non-SELECT statements"""
        self.executor._set_action_type('sql_query')

        invalid_statements = [
            "INSERT INTO users (name) VALUES ('test')",
            "UPDATE users SET name = 'new'",
            "DELETE FROM users",
            "CREATE TABLE test (id INT)",
            "DROP TABLE users",
        ]

        for sql in invalid_statements:
            with pytest.raises(ValueError, match="Only SELECT statements allowed for sql_query actions"):
                self.executor._validate_sql_safety(sql)

    def test_validate_sql_exec_rejects_invalid_statements(self):
        """Test that sql_exec actions reject invalid statements"""
        self.executor._set_action_type('sql_exec')

        invalid_statements = [
            "SELECT * FROM users",
            "UPDATE users SET name = 'new'",
            "CREATE TABLE test (id INT)",
            "DROP TABLE users",
            "ALTER TABLE users ADD column new_col INT",
        ]

        for sql in invalid_statements:
            with pytest.raises(ValueError, match="Only INSERT and DELETE statements allowed for sql_exec actions"):
                self.executor._validate_sql_safety(sql)

    def test_validate_sql_rejects_multiple_statements(self):
        """Test that multiple SQL statements are rejected"""
        self.executor._set_action_type('sql_query')

        dangerous_sql = [
            "SELECT * FROM users; DROP TABLE users;",
            "SELECT * FROM bookings; DELETE FROM bookings;",
            "INSERT INTO logs VALUES (1); SELECT * FROM users;",
        ]

        for sql in dangerous_sql:
            with pytest.raises(ValueError, match="Multiple SQL statements not allowed for security"):
                self.executor._validate_sql_safety(sql)

    def test_validate_sql_allows_trailing_semicolon(self):
        """Test that single trailing semicolon is allowed"""
        self.executor._set_action_type('sql_query')

        # These should be valid (single trailing semicolon)
        valid_sql = [
            "SELECT * FROM users;",
            "SELECT * FROM bookings;",
        ]

        for sql in valid_sql:
            # Should not raise exception
            self.executor._validate_sql_safety(sql)

    def test_validate_sql_rejects_dangerous_patterns(self):
        """Test that dangerous SQL patterns are rejected"""
        self.executor._set_action_type('sql_query')

        # Test patterns that would be caught by multiple statements check
        multiple_statement_patterns = [
            "SELECT * FROM users; DROP TABLE users",
        ]

        for sql in multiple_statement_patterns:
            with pytest.raises(ValueError, match="Multiple SQL statements not allowed for security"):
                self.executor._validate_sql_safety(sql)

        # Test patterns that would be caught by statement type check (non-SELECT)
        non_select_patterns = [
            "EXEC xp_cmdshell('rm -rf /')",
            "CALL dangerous_procedure()",
            "CREATE FUNCTION evil() RETURNS INT",
            "GRANT ALL ON *.* TO 'hacker'@'%'",
            "REVOKE SELECT ON users FROM 'user'",
            "TRUNCATE TABLE important_data",
            "ALTER TABLE users DROP COLUMN password",
        ]

        for sql in non_select_patterns:
            with pytest.raises(ValueError, match="Only SELECT statements allowed for sql_query actions"):
                self.executor._validate_sql_safety(sql)

        # Test patterns that would be caught by dangerous pattern check (valid SELECT statements)
        dangerous_select_patterns = [
            "SELECT load_file('/etc/passwd')",
            "SELECT * FROM users INTO OUTFILE '/tmp/users.txt'",
        ]

        for sql in dangerous_select_patterns:
            with pytest.raises(ValueError, match="Dangerous SQL pattern detected"):
                self.executor._validate_sql_safety(sql)


class TestActionTypeManagement:
    """Test action type setting and validation"""

    def setup_method(self):
        """Setup test fixtures"""
        self.mock_session = AsyncMock()
        self.executor = ActionExecutor(self.mock_session, "test-bot", 123)

    def test_set_action_type(self):
        """Test setting action type"""
        self.executor._set_action_type('sql_query')
        assert self.executor._current_action_type == 'sql_query'

        self.executor._set_action_type('sql_exec')
        assert self.executor._current_action_type == 'sql_exec'

    def test_action_type_affects_validation(self):
        """Test that action type affects SQL validation"""
        # Set as sql_query - should allow SELECT
        self.executor._set_action_type('sql_query')
        self.executor._validate_sql_safety("SELECT * FROM users")

        # Should reject INSERT
        with pytest.raises(ValueError):
            self.executor._validate_sql_safety("INSERT INTO users VALUES (1)")

        # Change to sql_exec - should allow INSERT
        self.executor._set_action_type('sql_exec')
        self.executor._validate_sql_safety("INSERT INTO users VALUES (1)")

        # Should reject SELECT
        with pytest.raises(ValueError):
            self.executor._validate_sql_safety("SELECT * FROM users")

    def test_action_type_affects_parameter_building(self):
        """Test that action type is required for parameter building"""
        # Without setting action type
        with pytest.raises(ValueError, match="Invalid action type: unknown"):
            self.executor._build_safe_parameters()

        # After setting valid action type
        self.executor._set_action_type('sql_query')
        params = self.executor._build_safe_parameters()
        assert "bot_id" in params


class TestRealWorldSQLExamples:
    """Test with realistic SQL examples from the booking system"""

    def setup_method(self):
        """Setup test fixtures"""
        self.mock_session = AsyncMock()
        self.executor = ActionExecutor(self.mock_session, "booking-bot-456", 78910)

    def test_booking_insert_sql(self):
        """Test booking insertion SQL"""
        self.executor._set_action_type('sql_exec')
        self.executor.set_context_var("service", "massage")
        self.executor.set_context_var("slot", "2024-01-15 14:00")

        sql = "INSERT INTO bookings(bot_id, user_id, service, slot) VALUES(:bot_id, :user_id, :service, :slot::timestamptz)"

        # Should validate successfully
        self.executor._validate_sql_safety(sql)

        # Should build correct parameters
        params = self.executor._build_safe_parameters()
        assert params["bot_id"] == "booking-bot-456"
        assert params["user_id"] == 78910
        assert params["service"] == "massage"
        assert params["slot"] == "2024-01-15 14:00"

    def test_booking_query_sql(self):
        """Test booking query SQL"""
        self.executor._set_action_type('sql_query')

        sql = "SELECT service, slot FROM bookings WHERE bot_id=:bot_id AND user_id=:user_id ORDER BY created_at DESC LIMIT 5"

        # Should validate successfully
        self.executor._validate_sql_safety(sql)

        # Should build correct parameters
        params = self.executor._build_safe_parameters()
        assert params["bot_id"] == "booking-bot-456"
        assert params["user_id"] == 78910

    def test_booking_cancel_sql(self):
        """Test booking cancellation SQL"""
        self.executor._set_action_type('sql_exec')

        sql = "DELETE FROM bookings WHERE bot_id=:bot_id AND user_id=:user_id AND id=(SELECT id FROM bookings WHERE bot_id=:bot_id AND user_id=:user_id ORDER BY created_at DESC LIMIT 1)"

        # Should validate successfully
        self.executor._validate_sql_safety(sql)

        # Should build correct parameters
        params = self.executor._build_safe_parameters()
        assert params["bot_id"] == "booking-bot-456"
        assert params["user_id"] == 78910

    def test_stats_query_sql(self):
        """Test statistics query SQL"""
        self.executor._set_action_type('sql_query')

        sql = "SELECT COUNT(*) as total_bookings, COUNT(DISTINCT user_id) as unique_users FROM bookings WHERE bot_id=:bot_id"

        # Should validate successfully
        self.executor._validate_sql_safety(sql)

        params = self.executor._build_safe_parameters()
        assert params["bot_id"] == "booking-bot-456"

    def test_complex_context_variables(self):
        """Test with complex context variables from wizard flow"""
        self.executor._set_action_type('sql_exec')

        # Variables that might come from wizard steps
        self.executor.set_context_var("service", "spa")
        self.executor.set_context_var("slot", "2024-02-20 10:30")
        self.executor.set_context_var("duration", 90)
        self.executor.set_context_var("notes", "First time customer")
        self.executor.set_context_var("confirmed", True)
        self.executor.set_context_var("metadata", {"source": "telegram", "promo_code": "WELCOME10"})

        params = self.executor._build_safe_parameters()

        # Basic parameters
        assert params["bot_id"] == "booking-bot-456"
        assert params["user_id"] == 78910

        # Simple variables
        assert params["service"] == "spa"
        assert params["slot"] == "2024-02-20 10:30"
        assert params["duration"] == 90
        assert params["notes"] == "First time customer"
        assert params["confirmed"] is True

        # Complex variable (JSON serialized)
        assert params["metadata"] == json.dumps({"source": "telegram", "promo_code": "WELCOME10"})


class TestEdgeCasesAndErrors:
    """Test edge cases and error conditions"""

    def setup_method(self):
        """Setup test fixtures"""
        self.mock_session = AsyncMock()
        self.executor = ActionExecutor(self.mock_session, "test", 999)

    def test_empty_sql_validation(self):
        """Test validation of empty SQL"""
        self.executor._set_action_type('sql_query')

        with pytest.raises(ValueError):
            self.executor._validate_sql_safety("")

    def test_whitespace_only_sql(self):
        """Test validation of whitespace-only SQL"""
        self.executor._set_action_type('sql_query')

        with pytest.raises(ValueError):
            self.executor._validate_sql_safety("   \n\t   ")

    def test_case_insensitive_validation(self):
        """Test that validation is case insensitive"""
        self.executor._set_action_type('sql_query')

        # These should all be valid
        valid_variants = [
            "SELECT * FROM users",
            "select * from users",
            "Select * From Users",
            "sElEcT * fRoM uSeRs",
        ]

        for sql in valid_variants:
            self.executor._validate_sql_safety(sql)

    def test_parameter_overwriting(self):
        """Test that context variables can overwrite built-in parameters"""
        self.executor._set_action_type('sql_query')

        # Try to set bot_id and user_id in context
        self.executor.set_context_var("bot_id", "malicious-bot")
        self.executor.set_context_var("user_id", 666)

        params = self.executor._build_safe_parameters()

        # Context variables overwrite built-in parameters (current behavior)
        assert params["bot_id"] == "malicious-bot"  # Context overrides
        assert params["user_id"] == 666    # Context overrides (as int)

    def test_parameter_name_conflicts(self):
        """Test handling of parameter name conflicts"""
        self.executor._set_action_type('sql_exec')

        # Set variables with same names as built-ins
        self.executor.set_context_var("bot_id", "context-bot")
        self.executor.set_context_var("user_id", "context-user")
        self.executor.set_context_var("custom_var", "custom-value")

        params = self.executor._build_safe_parameters()

        # Context variables override built-in parameters (current behavior)
        assert params["bot_id"] == "context-bot"
        assert params["user_id"] == "context-user"
        assert params["custom_var"] == "custom-value"