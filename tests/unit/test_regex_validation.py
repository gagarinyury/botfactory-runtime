"""Unit tests for regex validation functionality"""
import pytest
import re
from runtime.schemas import FlowStepValidation, FlowStep


class TestRegexValidation:
    """Test regex validation logic"""

    def test_simple_regex_patterns(self):
        """Test basic regex pattern validation"""
        # Email pattern
        email_validation = FlowStepValidation(
            regex=r"^[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}$",
            msg="Неправильный формат email"
        )

        # Test valid emails
        valid_emails = [
            "user@example.com",
            "test.email@domain.co.uk",
            "user123@test-domain.org"
        ]

        for email in valid_emails:
            assert re.match(email_validation.regex, email) is not None, f"Email {email} should be valid"

        # Test invalid emails
        invalid_emails = [
            "invalid-email",
            "@domain.com",
            "user@",
            # Note: user..name@domain.com actually matches the simple regex,
            # for a more strict email validation we'd need a more complex pattern
            "user@domain"  # Missing TLD
        ]

        for email in invalid_emails:
            assert re.match(email_validation.regex, email) is None, f"Email {email} should be invalid"

    def test_time_format_validation(self):
        """Test time format validation (HH:MM)"""
        time_validation = FlowStepValidation(
            regex=r"^([0-1][0-9]|2[0-3]):[0-5][0-9]$",
            msg="Формат времени: HH:MM (например, 14:30)"
        )

        # Valid times
        valid_times = ["00:00", "12:30", "23:59", "09:15", "16:45"]
        for time_str in valid_times:
            assert re.match(time_validation.regex, time_str) is not None, f"Time {time_str} should be valid"

        # Invalid times
        invalid_times = ["24:00", "12:60", "9:30", "12:5", "abc", "12:30:00"]
        for time_str in invalid_times:
            assert re.match(time_validation.regex, time_str) is None, f"Time {time_str} should be invalid"

    def test_datetime_validation(self):
        """Test datetime format validation (YYYY-MM-DD HH:MM)"""
        datetime_validation = FlowStepValidation(
            regex=r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$",
            msg="Формат: YYYY-MM-DD HH:MM (например, 2024-01-15 14:00)"
        )

        # Valid datetimes
        valid_datetimes = [
            "2024-01-15 14:00",
            "2023-12-31 23:59",
            "2025-06-01 09:00"
        ]
        for dt in valid_datetimes:
            assert re.match(datetime_validation.regex, dt) is not None, f"Datetime {dt} should be valid"

        # Invalid datetimes
        invalid_datetimes = [
            "24-01-15 14:00",  # Year too short
            "2024-1-15 14:00",  # Month single digit
            "2024-01-5 14:00",  # Day single digit
            "2024-01-15 4:00",  # Hour single digit
            "2024-01-15 14:0",  # Minute single digit
            "2024/01/15 14:00",  # Wrong separator
            "2024-01-15T14:00",  # Wrong time separator
        ]
        for dt in invalid_datetimes:
            assert re.match(datetime_validation.regex, dt) is None, f"Datetime {dt} should be invalid"

    def test_service_choice_validation(self):
        """Test service choice validation (limited options)"""
        service_validation = FlowStepValidation(
            regex=r"^(massage|spa|consultation)$",
            msg="Выберите: massage, spa, consultation"
        )

        # Valid choices
        valid_choices = ["massage", "spa", "consultation"]
        for choice in valid_choices:
            assert re.match(service_validation.regex, choice) is not None, f"Choice {choice} should be valid"

        # Invalid choices
        invalid_choices = [
            "Massage",  # Wrong case
            "massages",  # Plural
            "spa session",  # Extra words
            "therapy",  # Not in list
            ""  # Empty
        ]
        for choice in invalid_choices:
            assert re.match(service_validation.regex, choice) is None, f"Choice {choice} should be invalid"

    def test_phone_number_validation(self):
        """Test phone number validation (Russian format)"""
        phone_validation = FlowStepValidation(
            regex=r"^(\+7|8)[\d\s\-\(\)]{10,}$",
            msg="Формат: +7 (999) 123-45-67 или 8 999 123 45 67"
        )

        # Valid phone numbers
        valid_phones = [
            "+7 (999) 123-45-67",
            "+79991234567",
            "8 999 123 45 67",
            "89991234567",
            "+7-999-123-45-67"
        ]
        for phone in valid_phones:
            assert re.match(phone_validation.regex, phone) is not None, f"Phone {phone} should be valid"

        # Invalid phone numbers
        invalid_phones = [
            "7 999 123 45 67",  # Missing + or 8
            "+8 999 123 45 67",  # Wrong country code
            "+7 999",  # Too short
            "123-45-67"  # No country code
        ]
        for phone in invalid_phones:
            assert re.match(phone_validation.regex, phone) is None, f"Phone {phone} should be invalid"

    def test_yes_no_validation(self):
        """Test yes/no boolean validation"""
        yes_no_validation = FlowStepValidation(
            regex=r"^(да|нет|yes|no)$",
            msg="Ответьте: да, нет, yes или no"
        )

        # Valid answers
        valid_answers = ["да", "нет", "yes", "no"]
        for answer in valid_answers:
            assert re.match(yes_no_validation.regex, answer) is not None, f"Answer {answer} should be valid"

        # Invalid answers
        invalid_answers = [
            "Да",  # Wrong case
            "YES",  # Wrong case
            "y",   # Abbreviated
            "n",   # Abbreviated
            "maybe",  # Not boolean
            ""  # Empty
        ]
        for answer in invalid_answers:
            assert re.match(yes_no_validation.regex, answer) is None, f"Answer {answer} should be invalid"

    def test_numeric_validation(self):
        """Test numeric input validation"""
        # Integer validation
        integer_validation = FlowStepValidation(
            regex=r"^\d+$",
            msg="Введите целое число"
        )

        valid_integers = ["0", "1", "123", "999999"]
        for num in valid_integers:
            assert re.match(integer_validation.regex, num) is not None, f"Number {num} should be valid"

        invalid_integers = ["-1", "1.5", "abc", "12a", ""]
        for num in invalid_integers:
            assert re.match(integer_validation.regex, num) is None, f"Number {num} should be invalid"

        # Decimal validation
        decimal_validation = FlowStepValidation(
            regex=r"^\d+(\.\d{1,2})?$",
            msg="Введите число (до 2 знаков после запятой)"
        )

        valid_decimals = ["123", "123.4", "123.45", "0", "0.5"]
        for num in valid_decimals:
            assert re.match(decimal_validation.regex, num) is not None, f"Decimal {num} should be valid"

        invalid_decimals = ["123.456", "12.a", "abc", ".5", "123."]
        for num in invalid_decimals:
            assert re.match(decimal_validation.regex, num) is None, f"Decimal {num} should be invalid"

    def test_complex_regex_patterns(self):
        """Test complex regex patterns"""
        # UUID validation
        uuid_validation = FlowStepValidation(
            regex=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            msg="Введите UUID в формате xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
        )

        valid_uuid = "123e4567-e89b-12d3-a456-426614174000"
        assert re.match(uuid_validation.regex, valid_uuid) is not None

        invalid_uuids = [
            "123e4567-e89b-12d3-a456-42661417400",  # Too short
            "123e4567-e89b-12d3-a456-4266141740000",  # Too long
            "123e4567-e89b-12d3-a456-42661417400g",  # Invalid character
            "123e4567e89b12d3a456426614174000"  # Missing dashes
        ]
        for uuid_str in invalid_uuids:
            assert re.match(uuid_validation.regex, uuid_str) is None

        # URL validation (simplified)
        url_validation = FlowStepValidation(
            regex=r"^https?://[\w\.-]+\.\w{2,}(/.*)?$",
            msg="Введите URL (http:// или https://)"
        )

        valid_urls = [
            "https://example.com",
            "http://test.org/path",
            "https://sub.domain.com/path/to/page"
        ]
        for url in valid_urls:
            assert re.match(url_validation.regex, url) is not None, f"URL {url} should be valid"

        invalid_urls = [
            "ftp://example.com",  # Wrong protocol
            "https://example",  # No TLD
            "example.com",  # No protocol
            "https://.com"  # Invalid domain
        ]
        for url in invalid_urls:
            assert re.match(url_validation.regex, url) is None, f"URL {url} should be invalid"


class TestFlowStepWithValidation:
    """Test FlowStep integration with validation"""

    def test_flow_step_validation_integration(self):
        """Test that FlowStep correctly integrates with validation"""
        step = FlowStep(
            ask="Введите email",
            var="user_email",
            validate=FlowStepValidation(
                regex=r"^[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}$",
                msg="Неправильный формат email"
            )
        )

        # Test that validation is properly attached
        assert step.validate is not None
        assert step.validate.regex == r"^[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}$"
        assert step.validate.msg == "Неправильный формат email"

        # Test validation logic
        valid_email = "test@example.com"
        invalid_email = "invalid-email"

        assert re.match(step.validate.regex, valid_email) is not None
        assert re.match(step.validate.regex, invalid_email) is None

    def test_multiple_steps_different_validations(self):
        """Test multiple steps with different validation patterns"""
        email_step = FlowStep(
            ask="Email?",
            var="email",
            validate=FlowStepValidation(
                regex=r"^[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}$",
                msg="Неправильный email"
            )
        )

        time_step = FlowStep(
            ask="Время?",
            var="time",
            validate=FlowStepValidation(
                regex=r"^([0-1][0-9]|2[0-3]):[0-5][0-9]$",
                msg="Формат: HH:MM"
            )
        )

        service_step = FlowStep(
            ask="Услуга?",
            var="service",
            validate=FlowStepValidation(
                regex=r"^(massage|spa|consultation)$",
                msg="Выберите: massage, spa, consultation"
            )
        )

        # Test each step's validation
        assert re.match(email_step.validate.regex, "test@example.com") is not None
        assert re.match(time_step.validate.regex, "14:30") is not None
        assert re.match(service_step.validate.regex, "massage") is not None

        # Test invalid inputs
        assert re.match(email_step.validate.regex, "invalid") is None
        assert re.match(time_step.validate.regex, "25:00") is None
        assert re.match(service_step.validate.regex, "therapy") is None


class TestEdgeCasesAndErrors:
    """Test edge cases and error conditions in regex validation"""

    def test_empty_regex_pattern(self):
        """Test behavior with empty regex pattern"""
        validation = FlowStepValidation(regex="", msg="Empty pattern")

        # Empty regex should match empty string
        assert re.match(validation.regex, "") is not None
        # But also matches any string (not useful in practice)
        assert re.match(validation.regex, "anything") is not None

    def test_invalid_regex_pattern(self):
        """Test behavior with invalid regex patterns"""
        # These would cause regex compilation errors in real usage
        invalid_patterns = [
            r"[",  # Unclosed bracket
            r"(?P<invalid",  # Unclosed group
            r"*",  # Invalid quantifier
        ]

        for pattern in invalid_patterns:
            with pytest.raises(re.error):
                re.compile(pattern)

    def test_case_sensitive_patterns(self):
        """Test case sensitivity in regex patterns"""
        case_sensitive = FlowStepValidation(
            regex=r"^(Yes|No)$",
            msg="Answer Yes or No (case sensitive)"
        )

        # Exact case matches
        assert re.match(case_sensitive.regex, "Yes") is not None
        assert re.match(case_sensitive.regex, "No") is not None

        # Different case doesn't match
        assert re.match(case_sensitive.regex, "yes") is None
        assert re.match(case_sensitive.regex, "YES") is None
        assert re.match(case_sensitive.regex, "no") is None

    def test_whitespace_handling(self):
        """Test regex patterns with whitespace handling"""
        # Pattern that allows optional whitespace
        flexible_pattern = FlowStepValidation(
            regex=r"^\s*(massage|spa|consultation)\s*$",
            msg="Choose service (whitespace allowed)"
        )

        # Should match with leading/trailing whitespace
        assert re.match(flexible_pattern.regex, "massage") is not None
        assert re.match(flexible_pattern.regex, " massage ") is not None
        assert re.match(flexible_pattern.regex, "\tmassage\n") is not None

        # Strict pattern without whitespace handling
        strict_pattern = FlowStepValidation(
            regex=r"^(massage|spa|consultation)$",
            msg="Choose service (exact match)"
        )

        # Should not match with whitespace
        assert re.match(strict_pattern.regex, "massage") is not None
        assert re.match(strict_pattern.regex, " massage ") is None

    def test_unicode_support(self):
        """Test regex patterns with Unicode characters"""
        cyrillic_validation = FlowStepValidation(
            regex=r"^[а-яё]+$",
            msg="Введите русское слово"
        )

        # Valid Cyrillic words
        assert re.match(cyrillic_validation.regex, "привет") is not None
        assert re.match(cyrillic_validation.regex, "тест") is not None
        assert re.match(cyrillic_validation.regex, "ёж") is not None

        # Invalid (contains non-Cyrillic)
        assert re.match(cyrillic_validation.regex, "hello") is None
        assert re.match(cyrillic_validation.regex, "тест123") is None
        assert re.match(cyrillic_validation.regex, "тест test") is None