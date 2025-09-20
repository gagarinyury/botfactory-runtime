"""Test DSL engine router closure behavior"""
import pytest
from runtime.dsl_engine import DSLEngine

def test_build_router_closure():
    """Test that router correctly handles different intents without closure issues"""
    dsl_engine = DSLEngine()

    spec_json = {
        "intents": [
            {"cmd": "/a", "reply": "A"},
            {"cmd": "/b", "reply": "B"}
        ]
    }

    result = dsl_engine.build_router_from_spec(spec_json)

    # Router should be built successfully
    assert result["status"] == "ok"
    assert result["router_built"] is True
    assert result["intents_count"] == 2

    # Router configuration should contain handlers
    router_config = result["router_config"]
    assert "handlers" in router_config
    assert len(router_config["handlers"]) > 0

@pytest.mark.anyio
async def test_handle_commands_no_closure():
    """Test that handle function returns correct responses for different commands"""
    from runtime.dsl_engine import handle

    # Create mock spec for testing
    test_bot_id = "c3b88b65-623c-41b5-a3c9-8d56fcbc4413"

    # Test /start command
    reply_start = await handle(test_bot_id, "/start")
    assert "Привет" in reply_start

    # Test /help command
    reply_help = await handle(test_bot_id, "/help")
    assert "команд" in reply_help

    # Test unknown command
    reply_unknown = await handle(test_bot_id, "/unknown")
    assert "Не знаю эту команду" == reply_unknown

def test_router_config_structure():
    """Test that router configuration has expected structure"""
    dsl_engine = DSLEngine()

    spec_json = {
        "intents": [
            {"cmd": "/test", "reply": "Test response"}
        ],
        "flows": []
    }

    result = dsl_engine.build_router_from_spec(spec_json)

    assert result["status"] == "ok"
    assert "router_config" in result

    router_config = result["router_config"]
    assert router_config["type"] == "echo_router"
    assert "handlers" in router_config
    assert "fallback" in router_config

    # Check fallback configuration
    fallback = router_config["fallback"]
    assert fallback["action"] == "echo"
    assert "response" in fallback

def test_empty_spec():
    """Test handling of empty spec"""
    dsl_engine = DSLEngine()

    spec_json = {"intents": [], "flows": []}

    result = dsl_engine.build_router_from_spec(spec_json)

    assert result["status"] == "ok"
    assert result["router_built"] is True
    assert result["intents_count"] == 0
    assert result["flows_count"] == 0

def test_malformed_spec():
    """Test handling of malformed spec"""
    dsl_engine = DSLEngine()

    # Missing required fields
    spec_json = {"invalid": "data"}

    result = dsl_engine.build_router_from_spec(spec_json)

    # Should still build successfully with defaults
    assert result["status"] == "ok"
    assert result["router_built"] is True
    assert result["intents_count"] == 0
    assert result["flows_count"] == 0