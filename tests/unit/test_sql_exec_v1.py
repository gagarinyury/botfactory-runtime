"""Unit tests for action.sql_exec.v1 functionality"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from runtime.actions import ActionExecutor
from sqlalchemy.ext.asyncio import AsyncSession


class TestSqlExecV1:
    """Test action.sql_exec.v1 execution"""

    def setup_method(self):
        """Setup test fixtures"""
        self.mock_session = AsyncMock(spec=AsyncSession)
        self.bot_id = "test-bot"
        self.user_id = 12345
        self.executor = ActionExecutor(self.mock_session, self.bot_id, self.user_id)

    @pytest.mark.asyncio
    async def test_sql_exec_insert_success(self):
        """Test successful INSERT execution"""
        config = {
            "sql": "INSERT INTO bookings(bot_id, user_id, service) VALUES (:bot_id, :user_id, :service)"
        }

        # Set context variables
        self.executor.set_context_var("service", "massage")

        # Mock successful execution
        mock_result = MagicMock()
        mock_result.rowcount = 1
        self.mock_session.execute.return_value = mock_result

        with patch('runtime.actions.bot_sql_exec_total') as mock_counter, \
             patch('runtime.actions.dsl_action_latency_ms') as mock_histogram:

            result = await self.executor._execute_sql_exec(config)

            assert result["success"] is True
            assert result["status"] == "ok"
            assert result["rows"] == 1

            # Verify SQL execution
            self.mock_session.execute.assert_called_once()
            self.mock_session.commit.assert_called_once()

            # Verify metrics
            mock_counter.labels.assert_called_with(self.bot_id)
            mock_histogram.labels.assert_called_with("sql_exec")

    @pytest.mark.asyncio
    async def test_sql_exec_update_success(self):
        """Test successful UPDATE execution"""
        config = {
            "sql": "UPDATE bookings SET status = :status WHERE bot_id = :bot_id AND user_id = :user_id"
        }

        # Set context variables
        self.executor.set_context_var("status", "confirmed")

        # Mock successful execution
        mock_result = MagicMock()
        mock_result.rowcount = 2
        self.mock_session.execute.return_value = mock_result

        with patch('runtime.actions.bot_sql_exec_total'), \
             patch('runtime.actions.dsl_action_latency_ms'):

            result = await self.executor._execute_sql_exec(config)

            assert result["success"] is True
            assert result["status"] == "ok"
            assert result["rows"] == 2

    @pytest.mark.asyncio
    async def test_sql_exec_delete_success(self):
        """Test successful DELETE execution"""
        config = {
            "sql": "DELETE FROM bookings WHERE bot_id = :bot_id AND user_id = :user_id"
        }

        # Mock successful execution
        mock_result = MagicMock()
        mock_result.rowcount = 0  # No rows deleted
        self.mock_session.execute.return_value = mock_result

        with patch('runtime.actions.bot_sql_exec_total'), \
             patch('runtime.actions.dsl_action_latency_ms'):

            result = await self.executor._execute_sql_exec(config)

            assert result["success"] is True
            assert result["status"] == "ok"
            assert result["rows"] == 0

    @pytest.mark.asyncio
    async def test_sql_exec_select_rejected(self):
        """Test SELECT statements are rejected"""
        config = {
            "sql": "SELECT * FROM bookings WHERE bot_id = :bot_id"
        }

        with pytest.raises(ValueError, match="Only INSERT, UPDATE and DELETE statements allowed"):
            await self.executor._execute_sql_exec(config)

    @pytest.mark.asyncio
    async def test_sql_exec_dangerous_statement_rejected(self):
        """Test dangerous SQL statements are rejected"""
        dangerous_sqls = [
            "DROP TABLE bookings",
            "CREATE TABLE test (id INT)",
            "ALTER TABLE bookings ADD COLUMN test VARCHAR(50)",
            "TRUNCATE TABLE bookings",
            "GRANT ALL ON bookings TO user",
            "REVOKE ALL ON bookings FROM user"
        ]

        for sql in dangerous_sqls:
            config = {"sql": sql}

            with pytest.raises(ValueError, match="Dangerous SQL pattern detected"):
                await self.executor._execute_sql_exec(config)

    @pytest.mark.asyncio
    async def test_sql_exec_multiple_statements_rejected(self):
        """Test multiple SQL statements are rejected"""
        config = {
            "sql": "INSERT INTO bookings(bot_id, user_id) VALUES (:bot_id, :user_id); DROP TABLE users;"
        }

        with pytest.raises(ValueError, match="Multiple SQL statements not allowed"):
            await self.executor._execute_sql_exec(config)

    @pytest.mark.asyncio
    async def test_sql_exec_database_error_handling(self):
        """Test database error handling with rollback"""
        config = {
            "sql": "INSERT INTO bookings(bot_id, user_id, service) VALUES (:bot_id, :user_id, :service)"
        }

        # Set context variables
        self.executor.set_context_var("service", "massage")

        # Mock database error
        self.mock_session.execute.side_effect = Exception("Database connection failed")

        with patch('runtime.actions.bot_sql_exec_total'), \
             patch('runtime.actions.dsl_action_latency_ms'):

            with pytest.raises(Exception, match="Database connection failed"):
                await self.executor._execute_sql_exec(config)

            # Verify rollback was called
            self.mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_sql_exec_parameter_substitution(self):
        """Test parameter substitution works correctly"""
        config = {
            "sql": "INSERT INTO bookings(bot_id, user_id, service, slot, phone) VALUES (:bot_id, :user_id, :service, :slot, :phone)"
        }

        # Set context variables
        self.executor.set_context_var("service", "massage")
        self.executor.set_context_var("slot", "2024-12-25 14:30")
        self.executor.set_context_var("phone", "+79123456789")

        # Mock successful execution
        mock_result = MagicMock()
        mock_result.rowcount = 1
        self.mock_session.execute.return_value = mock_result

        with patch('runtime.actions.bot_sql_exec_total'), \
             patch('runtime.actions.dsl_action_latency_ms'):

            result = await self.executor._execute_sql_exec(config)

            assert result["success"] is True

            # Verify parameters were passed correctly
            call_args = self.mock_session.execute.call_args
            params = call_args[0][1]  # Second argument is parameters

            assert params["bot_id"] == self.bot_id
            assert params["user_id"] == self.user_id
            assert params["service"] == "massage"
            assert params["slot"] == "2024-12-25 14:30"
            assert params["phone"] == "+79123456789"

    @pytest.mark.asyncio
    async def test_sql_exec_complex_types_serialization(self):
        """Test complex types are serialized to JSON"""
        config = {
            "sql": "INSERT INTO bookings(bot_id, user_id, metadata) VALUES (:bot_id, :user_id, :metadata)"
        }

        # Set complex context variable
        metadata = {"preferences": ["massage", "hair"], "rating": 5}
        self.executor.set_context_var("metadata", metadata)

        # Mock successful execution
        mock_result = MagicMock()
        mock_result.rowcount = 1
        self.mock_session.execute.return_value = mock_result

        with patch('runtime.actions.bot_sql_exec_total'), \
             patch('runtime.actions.dsl_action_latency_ms'):

            result = await self.executor._execute_sql_exec(config)

            assert result["success"] is True

            # Verify complex type was serialized
            call_args = self.mock_session.execute.call_args
            params = call_args[0][1]

            import json
            assert params["metadata"] == json.dumps(metadata)

    @pytest.mark.asyncio
    async def test_sql_exec_logging(self):
        """Test SQL exec logging"""
        config = {
            "sql": "INSERT INTO bookings(bot_id, user_id) VALUES (:bot_id, :user_id)"
        }

        # Mock successful execution
        mock_result = MagicMock()
        mock_result.rowcount = 1
        self.mock_session.execute.return_value = mock_result

        with patch('runtime.actions.bot_sql_exec_total'), \
             patch('runtime.actions.dsl_handle_latency_ms'), \
             patch('runtime.actions.logger') as mock_logger:

            result = await self.executor._execute_sql_exec(config)

            assert result["success"] is True

            # Verify success logging
            mock_logger.info.assert_called_once()
            log_call = mock_logger.info.call_args
            assert log_call[0][0] == "sql_exec_executed"

            log_kwargs = log_call[1]
            assert log_kwargs["bot_id"] == self.bot_id
            assert log_kwargs["user_id"] == self.user_id
            assert log_kwargs["rows_affected"] == 1
            assert "duration_ms" in log_kwargs

    @pytest.mark.asyncio
    async def test_sql_exec_error_logging(self):
        """Test SQL exec error logging"""
        config = {
            "sql": "INSERT INTO bookings(bot_id, user_id) VALUES (:bot_id, :user_id)"
        }

        # Mock database error
        self.mock_session.execute.side_effect = Exception("Constraint violation")

        with patch('runtime.actions.bot_sql_exec_total'), \
             patch('runtime.actions.dsl_handle_latency_ms'), \
             patch('runtime.actions.logger') as mock_logger:

            with pytest.raises(Exception):
                await self.executor._execute_sql_exec(config)

            # Verify error logging
            mock_logger.error.assert_called_once()
            log_call = mock_logger.error.call_args
            assert log_call[0][0] == "sql_exec_failed"

            log_kwargs = log_call[1]
            assert log_kwargs["bot_id"] == self.bot_id
            assert log_kwargs["user_id"] == self.user_id
            assert log_kwargs["error"] == "Constraint violation"
            assert "duration_ms" in log_kwargs