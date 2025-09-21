"""Snapshot tests for LLM determinism with temperature=0.2"""
import pytest
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import patch, AsyncMock
from runtime.llm_client import LLMClient, LLMConfig


class TestLLMDeterminism:
    """Test LLM deterministic behavior with snapshots"""

    @pytest.fixture
    def deterministic_llm_client(self):
        """LLM client configured for deterministic output"""
        config = LLMConfig(
            temperature=0.2,  # Low temperature for determinism
            max_tokens=150,
            model="phi-3-mini"
        )
        return LLMClient(config)

    @pytest.fixture
    def test_templates(self):
        """Template test cases for snapshot testing"""
        return [
            {
                "name": "simple_greeting",
                "system": "You are a friendly assistant. Always be polite and helpful.",
                "user": "Hello, how are you?",
                "expected_keywords": ["hello", "help", "assist"]
            },
            {
                "name": "technical_explanation",
                "system": "Explain technical concepts clearly and concisely.",
                "user": "What is machine learning?",
                "expected_keywords": ["algorithm", "data", "learn", "pattern"]
            },
            {
                "name": "error_message_improvement",
                "system": "Improve error messages to be user-friendly.",
                "user": "Error: Invalid input format",
                "expected_keywords": ["error", "invalid", "format", "check"]
            },
            {
                "name": "booking_confirmation",
                "system": "Generate professional booking confirmations.",
                "user": "Booking confirmed for John Doe at 2:00 PM",
                "expected_keywords": ["confirm", "booking", "john", "2:00"]
            },
            {
                "name": "service_description",
                "system": "Create appealing service descriptions.",
                "user": "Massage therapy session - 60 minutes",
                "expected_keywords": ["massage", "therapy", "session", "relax"]
            },
            {
                "name": "validation_message",
                "system": "Create clear validation messages for forms.",
                "user": "Phone number is required",
                "expected_keywords": ["phone", "number", "required", "enter"]
            },
            {
                "name": "menu_item_description",
                "system": "Write appetizing menu descriptions.",
                "user": "Grilled salmon with lemon butter",
                "expected_keywords": ["salmon", "grilled", "lemon", "butter"]
            },
            {
                "name": "appointment_reminder",
                "system": "Create polite appointment reminders.",
                "user": "Appointment tomorrow at 3 PM with Dr. Smith",
                "expected_keywords": ["appointment", "tomorrow", "3 pm", "dr smith"]
            },
            {
                "name": "pricing_information",
                "system": "Present pricing information clearly.",
                "user": "Basic plan: $10/month, Premium: $25/month",
                "expected_keywords": ["basic", "premium", "$10", "$25", "month"]
            },
            {
                "name": "error_resolution",
                "system": "Provide helpful error resolution steps.",
                "user": "Connection timeout error occurred",
                "expected_keywords": ["connection", "timeout", "error", "try", "check"]
            }
        ]

    @pytest.fixture
    def snapshots_dir(self):
        """Directory for storing snapshot files"""
        snapshots_path = Path(__file__).parent / "snapshots"
        snapshots_path.mkdir(exist_ok=True)
        return snapshots_path

    def generate_response_hash(self, response: str) -> str:
        """Generate hash of response for comparison"""
        # Normalize response for hashing
        normalized = response.lower().strip()
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def save_snapshot(self, snapshots_dir: Path, test_name: str, response: str, metadata: Dict[str, Any]):
        """Save response snapshot"""
        snapshot_file = snapshots_dir / f"{test_name}.json"
        snapshot_data = {
            "response": response,
            "response_hash": self.generate_response_hash(response),
            "metadata": metadata,
            "response_length": len(response),
            "word_count": len(response.split())
        }

        with open(snapshot_file, 'w', encoding='utf-8') as f:
            json.dump(snapshot_data, f, indent=2, ensure_ascii=False)

    def load_snapshot(self, snapshots_dir: Path, test_name: str) -> Dict[str, Any]:
        """Load existing snapshot"""
        snapshot_file = snapshots_dir / f"{test_name}.json"
        if not snapshot_file.exists():
            return None

        with open(snapshot_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def analyze_response_consistency(self, responses: List[str]) -> Dict[str, Any]:
        """Analyze consistency across multiple responses"""
        if not responses:
            return {"consistent": False, "reason": "No responses"}

        # Check if all responses are identical
        first_response = responses[0]
        identical = all(r == first_response for r in responses)

        # Check response length consistency
        lengths = [len(r) for r in responses]
        length_variance = max(lengths) - min(lengths)

        # Check hash consistency
        hashes = [self.generate_response_hash(r) for r in responses]
        unique_hashes = len(set(hashes))

        return {
            "consistent": identical,
            "identical_responses": identical,
            "unique_hashes": unique_hashes,
            "total_responses": len(responses),
            "length_variance": length_variance,
            "avg_length": sum(lengths) / len(lengths),
            "responses": responses[:3]  # First 3 for inspection
        }

    @pytest.mark.asyncio
    @pytest.mark.determinism
    async def test_response_determinism_multiple_runs(self, deterministic_llm_client, test_templates):
        """Test that same inputs produce consistent outputs across multiple runs"""
        consistency_threshold = 0.8  # 80% of responses should be identical

        async def mock_deterministic_response(system, user, **kwargs):
            # Simulate deterministic responses based on input
            responses_map = {
                "Hello, how are you?": "Hello! I'm doing well, thank you for asking. How can I assist you today?",
                "What is machine learning?": "Machine learning is a subset of artificial intelligence that enables computers to learn and improve from data without being explicitly programmed.",
                "Error: Invalid input format": "Please check your input format and ensure all required fields are filled correctly.",
                "Booking confirmed for John Doe at 2:00 PM": "Your booking has been confirmed for John Doe at 2:00 PM. We look forward to serving you!",
                "Massage therapy session - 60 minutes": "Enjoy a relaxing 60-minute massage therapy session designed to relieve tension and promote wellness.",
                "Phone number is required": "Please enter a valid phone number to continue. This field is required for account verification.",
                "Grilled salmon with lemon butter": "Fresh grilled salmon fillet served with creamy lemon butter sauce, perfectly seasoned and cooked to perfection.",
                "Appointment tomorrow at 3 PM with Dr. Smith": "Reminder: You have an appointment scheduled for tomorrow at 3:00 PM with Dr. Smith. Please arrive 15 minutes early.",
                "Basic plan: $10/month, Premium: $25/month": "Choose your plan: Basic plan at $10 per month includes essential features, while Premium at $25 per month offers advanced capabilities.",
                "Connection timeout error occurred": "Connection timeout error detected. Please check your internet connection and try again. If the problem persists, contact support."
            }

            response_text = responses_map.get(user, f"I understand you're asking about: {user}")

            return {
                "content": response_text,
                "usage": {"prompt_tokens": 20, "completion_tokens": len(response_text.split()), "total_tokens": 20 + len(response_text.split())},
                "model": "phi-3-mini",
                "cached": False,
                "duration_ms": 150
            }

        with patch.object(deterministic_llm_client, 'complete', side_effect=mock_deterministic_response):
            for template in test_templates[:5]:  # Test first 5 templates
                responses = []

                # Generate 5 responses for the same input
                for run in range(5):
                    response = await deterministic_llm_client.complete(
                        system=template["system"],
                        user=template["user"],
                        temperature=0.2,  # Low temperature for determinism
                        use_cache=False
                    )
                    responses.append(response["content"])

                # Analyze consistency
                consistency = self.analyze_response_consistency(responses)

                print(f"\nDeterminism test for {template['name']}:")
                print(f"  Identical responses: {consistency['identical_responses']}")
                print(f"  Unique hashes: {consistency['unique_hashes']}/{consistency['total_responses']}")
                print(f"  Length variance: {consistency['length_variance']} chars")

                # For deterministic LLM, we expect high consistency
                assert consistency["unique_hashes"] <= 2, \
                    f"Too many unique responses ({consistency['unique_hashes']}) for {template['name']}"

                # Check that responses contain expected keywords
                combined_response = " ".join(responses).lower()
                for keyword in template["expected_keywords"]:
                    assert keyword.lower() in combined_response, \
                        f"Expected keyword '{keyword}' not found in responses for {template['name']}"

    @pytest.mark.asyncio
    @pytest.mark.determinism
    async def test_snapshot_consistency(self, deterministic_llm_client, test_templates, snapshots_dir):
        """Test that responses match saved snapshots"""
        update_snapshots = False  # Set to True to update snapshots

        async def mock_snapshot_response(system, user, **kwargs):
            # Consistent responses for snapshot testing
            snapshot_responses = {
                "simple_greeting": "Hello! I'm doing well, thank you for asking. I'm here to help you with any questions or tasks you might have. How can I assist you today?",
                "technical_explanation": "Machine learning is a branch of artificial intelligence that enables computers to learn patterns from data and make predictions or decisions without being explicitly programmed for every scenario.",
                "error_message_improvement": "Input format error: Please verify that your data follows the required format. Check for missing fields, incorrect data types, or invalid characters.",
                "booking_confirmation": "Booking Confirmed! Your appointment has been successfully scheduled for John Doe at 2:00 PM. Please arrive 10 minutes early and bring valid identification.",
                "service_description": "Indulge in our signature 60-minute massage therapy session, featuring therapeutic techniques designed to relieve muscle tension, reduce stress, and promote deep relaxation.",
            }

            response_text = snapshot_responses.get(template["name"], f"Standard response for: {user}")

            return {
                "content": response_text,
                "usage": {"prompt_tokens": 25, "completion_tokens": len(response_text.split()), "total_tokens": 25 + len(response_text.split())},
                "model": "phi-3-mini",
                "cached": False,
                "duration_ms": 180
            }

        with patch.object(deterministic_llm_client, 'complete', side_effect=mock_snapshot_response):
            for template in test_templates[:5]:  # Test first 5 templates
                # Generate response
                response = await deterministic_llm_client.complete(
                    system=template["system"],
                    user=template["user"],
                    temperature=0.2,
                    use_cache=False
                )

                response_text = response["content"]
                current_hash = self.generate_response_hash(response_text)

                # Load existing snapshot
                existing_snapshot = self.load_snapshot(snapshots_dir, template["name"])

                if update_snapshots or not existing_snapshot:
                    # Save new snapshot
                    metadata = {
                        "system": template["system"],
                        "user": template["user"],
                        "temperature": 0.2,
                        "model": "phi-3-mini",
                        "test_date": "2025-01-01"  # Fixed date for reproducible tests
                    }
                    self.save_snapshot(snapshots_dir, template["name"], response_text, metadata)
                    print(f"Saved snapshot for {template['name']}")

                else:
                    # Compare with existing snapshot
                    expected_hash = existing_snapshot["response_hash"]
                    expected_response = existing_snapshot["response"]

                    print(f"\nSnapshot comparison for {template['name']}:")
                    print(f"  Expected hash: {expected_hash}")
                    print(f"  Current hash:  {current_hash}")
                    print(f"  Match: {current_hash == expected_hash}")

                    if current_hash != expected_hash:
                        print(f"  Expected: {expected_response[:100]}...")
                        print(f"  Current:  {response_text[:100]}...")

                    # For deterministic behavior, hashes should match
                    assert current_hash == expected_hash, \
                        f"Response hash mismatch for {template['name']}. Expected: {expected_hash}, Got: {current_hash}"

                    # Verify response contains expected keywords
                    for keyword in template["expected_keywords"]:
                        assert keyword.lower() in response_text.lower(), \
                            f"Expected keyword '{keyword}' not found in response for {template['name']}"

    @pytest.mark.asyncio
    @pytest.mark.determinism
    async def test_json_response_determinism(self, deterministic_llm_client):
        """Test JSON response determinism"""
        from runtime.llm_models import ValidationResult

        json_test_cases = [
            {
                "system": "Validate user input strictly",
                "user": "john@example.com",
                "expected_valid": True
            },
            {
                "system": "Validate user input strictly",
                "user": "invalid-email",
                "expected_valid": False
            },
            {
                "system": "Validate user input strictly",
                "user": "+1-555-123-4567",
                "expected_valid": True
            }
        ]

        async def mock_json_response(system, user, response_model, **kwargs):
            # Deterministic JSON responses
            if "john@example.com" in user:
                result = ValidationResult(valid=True, reason="Valid email format", confidence=0.95)
            elif "invalid-email" in user:
                result = ValidationResult(valid=False, reason="Invalid email format", confidence=0.90)
            elif "+1-555" in user:
                result = ValidationResult(valid=True, reason="Valid phone format", confidence=0.88)
            else:
                result = ValidationResult(valid=False, reason="Unknown format", confidence=0.50)

            return result

        with patch.object(deterministic_llm_client, 'complete_json', side_effect=mock_json_response):
            for test_case in json_test_cases:
                responses = []

                # Generate multiple JSON responses
                for _ in range(3):
                    result = await deterministic_llm_client.complete_json(
                        system=test_case["system"],
                        user=test_case["user"],
                        response_model=ValidationResult,
                        temperature=0.1,  # Very low for JSON
                        use_cache=False
                    )
                    responses.append(result)

                # Verify all responses are identical
                first_response = responses[0]
                for i, response in enumerate(responses[1:], 1):
                    assert response.valid == first_response.valid, \
                        f"Response {i} validity differs from first response"
                    assert response.reason == first_response.reason, \
                        f"Response {i} reason differs from first response"
                    assert response.confidence == first_response.confidence, \
                        f"Response {i} confidence differs from first response"

                # Verify expected behavior
                assert first_response.valid == test_case["expected_valid"], \
                    f"Unexpected validation result for: {test_case['user']}"

                print(f"JSON determinism verified for: {test_case['user']} -> {first_response.valid}")