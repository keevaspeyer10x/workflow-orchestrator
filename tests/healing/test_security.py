"""Tests for SecurityScrubber - Phase 2 Pattern Memory & Lookup."""

import pytest
from datetime import datetime


class TestSecurityScrubber:
    """Tests for removing secrets and PII before storage."""

    def test_scrub_api_key_equals_format(self):
        """Scrubs api_key=value format."""
        from src.healing.security import SecurityScrubber

        scrubber = SecurityScrubber()
        result = scrubber.scrub("Error with api_key=sk-abc123def456ghijklmnop")
        assert "sk-abc123" not in result
        assert "<REDACTED>" in result

    def test_scrub_apikey_no_underscore(self):
        """Scrubs apikey format (no underscore)."""
        from src.healing.security import SecurityScrubber

        scrubber = SecurityScrubber()
        result = scrubber.scrub("apikey: 'my-secret-key-12345678901234'")
        assert "my-secret-key" not in result
        assert "<REDACTED>" in result

    def test_scrub_bearer_token(self):
        """Scrubs Authorization: Bearer token format."""
        from src.healing.security import SecurityScrubber

        scrubber = SecurityScrubber()
        result = scrubber.scrub("Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz")
        assert "eyJhbGc" not in result
        assert "<REDACTED>" in result

    def test_scrub_token_equals(self):
        """Scrubs token=value format."""
        from src.healing.security import SecurityScrubber

        scrubber = SecurityScrubber()
        result = scrubber.scrub("token=ghp_abcdefghij1234567890abcdefghij1234")
        assert "ghp_abcdef" not in result
        assert "<REDACTED>" in result

    def test_scrub_password(self):
        """Scrubs password=value format."""
        from src.healing.security import SecurityScrubber

        scrubber = SecurityScrubber()
        result = scrubber.scrub("Connecting with password=MyS3cr3tP@ss!")
        assert "MyS3cr3t" not in result
        assert "<REDACTED>" in result

    def test_scrub_passwd(self):
        """Scrubs passwd=value format."""
        from src.healing.security import SecurityScrubber

        scrubber = SecurityScrubber()
        result = scrubber.scrub("passwd: 'hunter2'")
        assert "hunter2" not in result
        assert "<REDACTED>" in result

    def test_scrub_aws_access_key(self):
        """Scrubs AWS access key (AKIA prefix)."""
        from src.healing.security import SecurityScrubber

        scrubber = SecurityScrubber()
        result = scrubber.scrub("Error using AKIAIOSFODNN7EXAMPLE")
        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert "<AWS_KEY>" in result

    def test_scrub_private_key_pem(self):
        """Scrubs PEM format private keys."""
        from src.healing.security import SecurityScrubber

        scrubber = SecurityScrubber()
        pem_key = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA2Z3qX2BTLS4e0ek5d...
-----END RSA PRIVATE KEY-----"""
        result = scrubber.scrub(f"Key is: {pem_key}")
        assert "MIIEpAIBAAK" not in result
        assert "<PRIVATE_KEY>" in result

    def test_scrub_connection_string_postgres(self):
        """Scrubs postgres connection strings."""
        from src.healing.security import SecurityScrubber

        scrubber = SecurityScrubber()
        result = scrubber.scrub("postgres://user:password@localhost:5432/db")
        assert "user:password" not in result
        assert "postgres://<REDACTED>" in result

    def test_scrub_connection_string_mysql(self):
        """Scrubs mysql connection strings."""
        from src.healing.security import SecurityScrubber

        scrubber = SecurityScrubber()
        result = scrubber.scrub("mysql://admin:secret@db.example.com/mydb")
        assert "admin:secret" not in result
        assert "mysql://<REDACTED>" in result

    def test_scrub_connection_string_mongodb(self):
        """Scrubs mongodb connection strings."""
        from src.healing.security import SecurityScrubber

        scrubber = SecurityScrubber()
        result = scrubber.scrub("mongodb://root:pass123@mongo.cluster.local/admin")
        assert "root:pass123" not in result
        assert "mongodb://<REDACTED>" in result

    def test_scrub_email_address(self):
        """Scrubs email addresses (PII)."""
        from src.healing.security import SecurityScrubber

        scrubber = SecurityScrubber()
        result = scrubber.scrub("Contact admin@example.com for support")
        assert "admin@example.com" not in result
        assert "<EMAIL>" in result

    def test_scrub_multiple_secrets(self):
        """Scrubs text with multiple different secrets."""
        from src.healing.security import SecurityScrubber

        scrubber = SecurityScrubber()
        text = """
        API key: api_key=sk-1234567890abcdef12345678
        Token: token=ghp_abcdefghij1234567890abcdef
        AWS: AKIAIOSFODNN7EXAMPLE
        Email: user@company.com
        Database: postgres://admin:secret@localhost/db
        """
        result = scrubber.scrub(text)
        assert "sk-1234" not in result
        assert "ghp_abcdef" not in result
        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert "user@company.com" not in result
        assert "admin:secret" not in result

    def test_scrub_no_secrets(self):
        """Returns text unchanged when no secrets present."""
        from src.healing.security import SecurityScrubber

        scrubber = SecurityScrubber()
        text = "Hello world! This is a normal error message."
        result = scrubber.scrub(text)
        assert result == text

    def test_scrub_preserves_structure(self):
        """Preserves text structure while scrubbing."""
        from src.healing.security import SecurityScrubber

        scrubber = SecurityScrubber()
        text = "Line 1: api_key=secret123456789012345678\nLine 2: Error details"
        result = scrubber.scrub(text)
        assert "Line 1:" in result
        assert "Line 2: Error details" in result
        assert "\n" in result

    def test_scrub_error_event(self):
        """Scrubs all text fields in an ErrorEvent."""
        from src.healing.security import SecurityScrubber
        from src.healing.models import ErrorEvent

        scrubber = SecurityScrubber()
        error = ErrorEvent(
            error_id="err-123",
            timestamp=datetime.utcnow(),
            source="subprocess",
            description="Failed with api_key=sk-secret123456789012345",
            stack_trace="at function() password=hunter2",
        )
        result = scrubber.scrub_error(error)

        assert "sk-secret" not in result.description
        assert "hunter2" not in result.stack_trace
        assert result.error_id == "err-123"  # Non-text fields preserved

    def test_scrub_error_event_with_none_fields(self):
        """Handles ErrorEvent with None fields."""
        from src.healing.security import SecurityScrubber
        from src.healing.models import ErrorEvent

        scrubber = SecurityScrubber()
        error = ErrorEvent(
            error_id="err-456",
            timestamp=datetime.utcnow(),
            source="hook",
            description="Simple error",
            stack_trace=None,
        )
        result = scrubber.scrub_error(error)

        assert result.description == "Simple error"
        assert result.stack_trace is None

    def test_scrub_empty_string(self):
        """Handles empty string input."""
        from src.healing.security import SecurityScrubber

        scrubber = SecurityScrubber()
        result = scrubber.scrub("")
        assert result == ""

    def test_scrub_case_insensitive(self):
        """Scrubs secrets regardless of case."""
        from src.healing.security import SecurityScrubber

        scrubber = SecurityScrubber()
        result = scrubber.scrub("API_KEY=secret12345678901234567890")
        assert "secret12345" not in result
        assert "<REDACTED>" in result

        result2 = scrubber.scrub("PASSWORD=MySecret")
        assert "MySecret" not in result2
        assert "<REDACTED>" in result2
