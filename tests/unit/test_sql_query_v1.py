"""Unit tests for action.sql_query.v1 functionality"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from runtime.actions import ActionExecutor
from sqlalchemy.ext.asyncio import AsyncSession


class TestSqlQueryV1:
    """Test action.sql_query.v1 execution"""

    def setup_method(self):
        """Setup test fixtures"""
        self.mock_session = AsyncMock(spec=AsyncSession)
        self.bot_id = "test-bot"
        self.user_id = 12345
        self.executor = ActionExecutor(self.mock_session, self.bot_id, self.user_id)

    @pytest.mark.asyncio
    async def test_sql_query_list_of_dicts_mode(self):
        """Test default mode returns list of dicts"""
        config = {
            "sql": "SELECT service, slot FROM bookings WHERE bot_id = :bot_id AND user_id = :user_id ORDER BY slot DESC LIMIT 5",
            "result_var": "bookings"
        }

        # Mock result
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("massage", "2024-12-25 14:30"),
            ("hair", "2024-12-26 10:00")
        ]
        mock_result.keys.return_value = ["service", "slot"]
        self.mock_session.execute.return_value = mock_result

        with patch('runtime.actions.bot_sql_query_total') as mock_counter, \
             patch('runtime.actions.dsl_action_latency_ms') as mock_histogram:

            result = await self.executor._execute_sql_query(config)

            assert result["success"] is True
            assert result["rows"] == 2
            assert result["var"] == "bookings"

            # Check context was set correctly
            bookings = self.executor.context["bookings"]
            assert len(bookings) == 2
            assert bookings[0] == {"service": "massage", "slot": "2024-12-25 14:30"}
            assert bookings[1] == {"service": "hair", "slot": "2024-12-26 10:00"}

            # Verify metrics
            mock_counter.labels.assert_called_with(self.bot_id)
            mock_histogram.labels.assert_called_with("sql_query")

    @pytest.mark.asyncio
    async def test_sql_query_scalar_mode(self):
        """Test scalar mode returns single value"""
        config = {
            "sql": "SELECT slot FROM bookings WHERE bot_id = :bot_id AND user_id = :user_id ORDER BY slot DESC LIMIT 1",
            "result_var": "last_slot",
            "scalar": True
        }

        # Mock result with single value
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("2024-12-25 14:30",)]
        self.mock_session.execute.return_value = mock_result

        with patch('runtime.actions.bot_sql_query_total'), \
             patch('runtime.actions.dsl_action_latency_ms'):

            result = await self.executor._execute_sql_query(config)

            assert result["success"] is True
            assert result["rows"] == 1
            assert result["var"] == "last_slot"

            # Check scalar value was set
            assert self.executor.context["last_slot"] == "2024-12-25 14:30"

    @pytest.mark.asyncio
    async def test_sql_query_scalar_mode_empty_result(self):
        """Test scalar mode with empty result returns None"""
        config = {
            "sql": "SELECT slot FROM bookings WHERE bot_id = :bot_id AND user_id = :user_id ORDER BY slot DESC LIMIT 1",
            "result_var": "last_slot",
            "scalar": True
        }

        # Mock empty result
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        self.mock_session.execute.return_value = mock_result

        with patch('runtime.actions.bot_sql_query_total'), \
             patch('runtime.actions.dsl_action_latency_ms'):

            result = await self.executor._execute_sql_query(config)

            assert result["success"] is True
            assert result["rows"] == 0
            assert self.executor.context["last_slot"] is None

    @pytest.mark.asyncio
    async def test_sql_query_flatten_mode(self):
        """Test flatten mode returns list of scalar values"""
        config = {
            "sql": "SELECT service FROM bookings WHERE bot_id = :bot_id AND user_id = :user_id ORDER BY slot DESC LIMIT 5",
            "result_var": "services",
            "flatten": True
        }

        # Mock result with single column
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("massage",), ("hair",), ("cosmo",)]
        mock_result.keys.return_value = ["service"]
        self.mock_session.execute.return_value = mock_result

        with patch('runtime.actions.bot_sql_query_total'), \
             patch('runtime.actions.dsl_action_latency_ms'):

            result = await self.executor._execute_sql_query(config)

            assert result["success"] is True
            assert result["rows"] == 3
            assert result["var"] == "services"

            # Check flattened list was set
            services = self.executor.context["services"]
            assert services == ["massage", "hair", "cosmo"]

    @pytest.mark.asyncio
    async def test_sql_query_flatten_mode_multiple_columns_fallback(self):
        """Test flatten mode with multiple columns falls back to list of dicts"""
        config = {
            "sql": "SELECT service, slot FROM bookings WHERE bot_id = :bot_id AND user_id = :user_id",
            "result_var": "data",
            "flatten": True
        }

        # Mock result with multiple columns
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("massage", "2024-12-25")]
        mock_result.keys.return_value = ["service", "slot"]
        self.mock_session.execute.return_value = mock_result

        with patch('runtime.actions.bot_sql_query_total'), \
             patch('runtime.actions.dsl_action_latency_ms'):

            result = await self.executor._execute_sql_query(config)

            assert result["success"] is True
            # Should fall back to list of dicts mode
            data = self.executor.context["data"]
            assert data == [{"service": "massage", "slot": "2024-12-25"}]

    @pytest.mark.asyncio
    async def test_sql_query_with_statement_allowed(self):
        """Test WITH statements are allowed"""
        config = {
            "sql": "WITH recent AS (SELECT * FROM bookings WHERE created_at > NOW() - INTERVAL '7 days') SELECT service FROM recent WHERE bot_id = :bot_id",
            "result_var": "recent_services"
        }

        # Mock result
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("massage",)]
        mock_result.keys.return_value = ["service"]
        self.mock_session.execute.return_value = mock_result

        with patch('runtime.actions.bot_sql_query_total'), \
             patch('runtime.actions.dsl_action_latency_ms'):

            result = await self.executor._execute_sql_query(config)

            assert result["success"] is True
            assert result["rows"] == 1

    @pytest.mark.asyncio
    async def test_sql_query_insert_rejected(self):
        """Test INSERT statements are rejected"""
        config = {
            "sql": "INSERT INTO bookings(bot_id, user_id) VALUES (:bot_id, :user_id)",
            "result_var": "result"
        }

        with pytest.raises(ValueError, match="Only SELECT and WITH statements allowed"):
            await self.executor._execute_sql_query(config)

    @pytest.mark.asyncio
    async def test_sql_query_multiple_statements_rejected(self):
        """Test multiple SQL statements are rejected"""
        config = {
            "sql": "SELECT * FROM bookings; DROP TABLE users;",
            "result_var": "result"
        }

        with pytest.raises(ValueError, match="Multiple SQL statements not allowed"):
            await self.executor._execute_sql_query(config)

    @pytest.mark.asyncio
    async def test_sql_query_dangerous_statements_rejected(self):
        """Test dangerous SQL statements are rejected"""
        dangerous_sqls = [
            "SELECT * FROM bookings; DROP TABLE users",
            "SELECT *, (SELECT password FROM users) FROM bookings"
        ]

        for sql in dangerous_sqls:
            config = {"sql": sql, "result_var": "result"}

            with pytest.raises(ValueError):
                await self.executor._execute_sql_query(config)

    @pytest.mark.asyncio
    async def test_sql_query_automatic_limit_protection(self):
        """Test automatic LIMIT protection is added"""
        config = {
            "sql": "SELECT * FROM bookings WHERE bot_id = :bot_id",
            "result_var": "bookings"
        }

        # Mock result
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_result.keys.return_value = []
        self.mock_session.execute.return_value = mock_result

        with patch('runtime.actions.bot_sql_query_total'), \
             patch('runtime.actions.dsl_action_latency_ms'):

            await self.executor._execute_sql_query(config)

            # Check that LIMIT was added to the SQL
            call_args = self.mock_session.execute.call_args
            executed_sql = str(call_args[0][0])
            assert "LIMIT 100" in executed_sql

    @pytest.mark.asyncio
    async def test_sql_query_existing_limit_preserved(self):
        """Test existing LIMIT is preserved"""
        config = {
            "sql": "SELECT * FROM bookings WHERE bot_id = :bot_id LIMIT 5",
            "result_var": "bookings"
        }

        # Mock result
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_result.keys.return_value = []
        self.mock_session.execute.return_value = mock_result

        with patch('runtime.actions.bot_sql_query_total'), \
             patch('runtime.actions.dsl_action_latency_ms'):

            await self.executor._execute_sql_query(config)

            # Check that original LIMIT 5 was preserved
            call_args = self.mock_session.execute.call_args
            executed_sql = str(call_args[0][0])
            assert "LIMIT 5" in executed_sql
            assert "LIMIT 100" not in executed_sql

    @pytest.mark.asyncio
    async def test_sql_query_parameter_substitution(self):
        """Test parameter substitution works correctly"""
        config = {
            "sql": "SELECT * FROM bookings WHERE bot_id = :bot_id AND user_id = :user_id AND service = :service",
            "result_var": "bookings"
        }

        # Set context variables
        self.executor.set_context_var("service", "massage")

        # Mock result
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_result.keys.return_value = []
        self.mock_session.execute.return_value = mock_result

        with patch('runtime.actions.bot_sql_query_total'), \
             patch('runtime.actions.dsl_action_latency_ms'):

            result = await self.executor._execute_sql_query(config)

            assert result["success"] is True

            # Verify parameters were passed correctly
            call_args = self.mock_session.execute.call_args
            params = call_args[0][1]  # Second argument is parameters

            assert params["bot_id"] == self.bot_id
            assert params["user_id"] == self.user_id
            assert params["service"] == "massage"

    @pytest.mark.asyncio
    async def test_sql_query_empty_result(self):
        """Test empty result handling"""
        config = {
            "sql": "SELECT * FROM bookings WHERE bot_id = :bot_id",
            "result_var": "bookings"
        }

        # Mock empty result
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_result.keys.return_value = []
        self.mock_session.execute.return_value = mock_result

        with patch('runtime.actions.bot_sql_query_total'), \
             patch('runtime.actions.dsl_action_latency_ms'):

            result = await self.executor._execute_sql_query(config)

            assert result["success"] is True
            assert result["rows"] == 0
            assert self.executor.context["bookings"] == []

    @pytest.mark.asyncio
    async def test_sql_query_database_error_handling(self):
        """Test database error handling"""
        config = {
            "sql": "SELECT * FROM bookings WHERE bot_id = :bot_id",
            "result_var": "bookings"
        }

        # Mock database error
        self.mock_session.execute.side_effect = Exception("Database connection failed")

        with patch('runtime.actions.bot_sql_query_total'), \
             patch('runtime.actions.dsl_action_latency_ms'):

            with pytest.raises(Exception, match="Database connection failed"):
                await self.executor._execute_sql_query(config)

    @pytest.mark.asyncio
    async def test_sql_query_logging(self):
        """Test SQL query logging"""
        config = {
            "sql": "SELECT * FROM bookings WHERE bot_id = :bot_id",
            "result_var": "bookings"
        }

        # Mock result
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("massage", "2024-12-25")]
        mock_result.keys.return_value = ["service", "slot"]
        self.mock_session.execute.return_value = mock_result

        with patch('runtime.actions.bot_sql_query_total'), \
             patch('runtime.actions.dsl_action_latency_ms'), \
             patch('runtime.actions.logger') as mock_logger:

            result = await self.executor._execute_sql_query(config)

            assert result["success"] is True

            # Verify success logging
            mock_logger.info.assert_called_once()
            log_call = mock_logger.info.call_args
            assert log_call[0][0] == "sql_query_executed"

            log_kwargs = log_call[1]
            assert log_kwargs["bot_id"] == self.bot_id
            assert log_kwargs["user_id"] == self.user_id
            assert log_kwargs["rows_count"] == 1
            assert log_kwargs["result_var"] == "bookings"
            assert log_kwargs["scalar"] is False
            assert log_kwargs["flatten"] is False
            assert "duration_ms" in log_kwargs

    @pytest.mark.asyncio
    async def test_sql_query_error_logging(self):
        """Test SQL query error logging"""
        config = {
            "sql": "SELECT * FROM bookings WHERE bot_id = :bot_id",
            "result_var": "bookings"
        }

        # Mock database error
        self.mock_session.execute.side_effect = Exception("Table does not exist")

        with patch('runtime.actions.bot_sql_query_total'), \
             patch('runtime.actions.dsl_action_latency_ms'), \
             patch('runtime.actions.logger') as mock_logger:

            with pytest.raises(Exception):
                await self.executor._execute_sql_query(config)

            # Verify error logging
            mock_logger.error.assert_called_once()
            log_call = mock_logger.error.call_args
            assert log_call[0][0] == "sql_query_failed"

            log_kwargs = log_call[1]
            assert log_kwargs["bot_id"] == self.bot_id
            assert log_kwargs["user_id"] == self.user_id
            assert log_kwargs["error"] == "Table does not exist"
            assert "duration_ms" in log_kwargs