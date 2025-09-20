"""Test DSL spec validation"""
import pytest
from runtime.dsl_engine import DSLEngine

def test_empty_intents_valid():
    """Test that empty intents array is valid"""
    dsl_engine = DSLEngine()

    spec_json = {
        "intents": [],
        "flows": []
    }

    result = dsl_engine.build_router_from_spec(spec_json)

    assert result["status"] == "ok"
    assert result["router_built"] is True
    assert result["intents_count"] == 0

def test_valid_intent_structure():
    """Test valid intent structure"""
    dsl_engine = DSLEngine()

    spec_json = {
        "intents": [
            {"cmd": "/start", "reply": "Hello!"},
            {"cmd": "/help", "reply": "Help message"}
        ],
        "flows": []
    }

    result = dsl_engine.build_router_from_spec(spec_json)

    assert result["status"] == "ok"
    assert result["router_built"] is True
    assert result["intents_count"] == 2

def test_intent_missing_cmd():
    """Test intent without cmd field"""
    dsl_engine = DSLEngine()

    spec_json = {
        "intents": [
            {"reply": "Hello!"}  # Missing cmd
        ],
        "flows": []
    }

    # Current implementation should still work (no strict validation)
    result = dsl_engine.build_router_from_spec(spec_json)

    assert result["status"] == "ok"
    assert result["router_built"] is True

def test_intent_missing_reply():
    """Test intent without reply field"""
    dsl_engine = DSLEngine()

    spec_json = {
        "intents": [
            {"cmd": "/start"}  # Missing reply
        ],
        "flows": []
    }

    # Current implementation should still work
    result = dsl_engine.build_router_from_spec(spec_json)

    assert result["status"] == "ok"
    assert result["router_built"] is True

def test_invalid_intent_type():
    """Test invalid intent type (not object)"""
    dsl_engine = DSLEngine()

    spec_json = {
        "intents": [
            "invalid_intent",  # Should be object
            {"cmd": "/start", "reply": "Hello!"}
        ],
        "flows": []
    }

    # Current implementation should handle gracefully
    result = dsl_engine.build_router_from_spec(spec_json)

    assert result["status"] == "ok"
    assert result["router_built"] is True

def test_jsonb_config_validation_valid():
    """Test valid JSONB configuration validation"""
    dsl_engine = DSLEngine()

    valid_config = {
        "routes": [
            {"path": "/test", "method": "GET"},
            {"path": "/api/data", "method": "POST"}
        ]
    }

    is_valid, message = dsl_engine.validate_jsonb_config(valid_config)

    assert is_valid is True
    assert message == "Valid configuration"

def test_jsonb_config_validation_missing_routes():
    """Test JSONB config without routes"""
    dsl_engine = DSLEngine()

    config_without_routes = {
        "other": "data"
    }

    is_valid, message = dsl_engine.validate_jsonb_config(config_without_routes)

    # Should be valid (routes defaults to empty list)
    assert is_valid is True

def test_jsonb_config_validation_invalid_routes_type():
    """Test JSONB config with invalid routes type"""
    dsl_engine = DSLEngine()

    invalid_config = {
        "routes": "should_be_list"
    }

    is_valid, message = dsl_engine.validate_jsonb_config(invalid_config)

    assert is_valid is False
    assert "Routes must be a list" in message

def test_jsonb_config_validation_route_missing_path():
    """Test JSONB config with route missing path"""
    dsl_engine = DSLEngine()

    invalid_config = {
        "routes": [
            {"method": "GET"}  # Missing path
        ]
    }

    is_valid, message = dsl_engine.validate_jsonb_config(invalid_config)

    assert is_valid is False
    assert "missing required 'path' field" in message

def test_jsonb_config_validation_invalid_route_type():
    """Test JSONB config with invalid route type"""
    dsl_engine = DSLEngine()

    invalid_config = {
        "routes": [
            "invalid_route"  # Should be dict
        ]
    }

    is_valid, message = dsl_engine.validate_jsonb_config(invalid_config)

    assert is_valid is False
    assert "must be a dictionary" in message

def test_jsonb_config_validation_invalid_json_string():
    """Test JSONB config validation with invalid JSON string"""
    dsl_engine = DSLEngine()

    invalid_json = "{'invalid': json}"  # Should use double quotes

    is_valid, message = dsl_engine.validate_jsonb_config(invalid_json)

    assert is_valid is False
    assert "Invalid JSON" in message

def test_jsonb_config_validation_not_dict():
    """Test JSONB config that's not a dictionary"""
    dsl_engine = DSLEngine()

    invalid_config = ["should", "be", "dict"]

    is_valid, message = dsl_engine.validate_jsonb_config(invalid_config)

    assert is_valid is False
    assert "Configuration must be a dictionary" in message

def test_build_router_from_jsonb_valid():
    """Test building router from valid JSONB config"""
    dsl_engine = DSLEngine()

    valid_config = {
        "routes": [
            {"path": "/test", "method": "GET"},
            {"path": "/api/data", "method": "POST"}
        ]
    }

    router = dsl_engine.build_router_from_jsonb(valid_config)

    # Should return a valid FastAPI router
    assert router is not None
    # Router should be an APIRouter instance
    from fastapi import APIRouter
    assert isinstance(router, APIRouter)

def test_build_router_from_jsonb_invalid():
    """Test building router from invalid JSONB config"""
    dsl_engine = DSLEngine()

    invalid_config = "invalid json"

    router = dsl_engine.build_router_from_jsonb(invalid_config)

    # Should return empty router on error
    assert router is not None
    from fastapi import APIRouter
    assert isinstance(router, APIRouter)

def test_spec_with_flows():
    """Test spec with flows field"""
    dsl_engine = DSLEngine()

    spec_json = {
        "intents": [
            {"cmd": "/start", "reply": "Hello!"}
        ],
        "flows": [
            {"name": "test_flow", "steps": []}
        ]
    }

    result = dsl_engine.build_router_from_spec(spec_json)

    assert result["status"] == "ok"
    assert result["router_built"] is True
    assert result["intents_count"] == 1
    assert result["flows_count"] == 1

def test_spec_missing_intents():
    """Test spec without intents field"""
    dsl_engine = DSLEngine()

    spec_json = {
        "flows": []
    }

    result = dsl_engine.build_router_from_spec(spec_json)

    assert result["status"] == "ok"
    assert result["router_built"] is True
    assert result["intents_count"] == 0

def test_spec_missing_flows():
    """Test spec without flows field"""
    dsl_engine = DSLEngine()

    spec_json = {
        "intents": [
            {"cmd": "/start", "reply": "Hello!"}
        ]
    }

    result = dsl_engine.build_router_from_spec(spec_json)

    assert result["status"] == "ok"
    assert result["router_built"] is True
    assert result["flows_count"] == 0

def test_complex_intent_structure():
    """Test complex intent with additional fields"""
    dsl_engine = DSLEngine()

    spec_json = {
        "intents": [
            {
                "cmd": "/start",
                "reply": "Welcome!",
                "description": "Start command",
                "parameters": ["param1", "param2"],
                "keyboard": [["Button 1", "Button 2"]]
            }
        ],
        "flows": []
    }

    result = dsl_engine.build_router_from_spec(spec_json)

    assert result["status"] == "ok"
    assert result["router_built"] is True
    assert result["intents_count"] == 1

def test_unicode_in_spec():
    """Test spec with Unicode characters"""
    dsl_engine = DSLEngine()

    spec_json = {
        "intents": [
            {"cmd": "/привет", "reply": "Здравствуй! 🤖"},
            {"cmd": "/help", "reply": "Помощь по боту"}
        ],
        "flows": []
    }

    result = dsl_engine.build_router_from_spec(spec_json)

    assert result["status"] == "ok"
    assert result["router_built"] is True
    assert result["intents_count"] == 2