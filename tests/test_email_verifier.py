# tests/test_email_verifier.py
import pytest
from src.email_verifier import EmailVerifier, VerificationStatus, filter_valid_emails


@pytest.fixture
def verifier():
    return EmailVerifier(verify_smtp=False)  # Don't do SMTP checks in tests


class TestSyntaxValidation:
    def test_valid_email_syntax(self, verifier):
        valid, reason = verifier._validate_syntax("test@example.com")
        assert valid is True

    def test_invalid_email_no_at(self, verifier):
        valid, reason = verifier._validate_syntax("testexample.com")
        assert valid is False

    def test_invalid_email_no_domain(self, verifier):
        valid, reason = verifier._validate_syntax("test@")
        assert valid is False

    def test_invalid_email_consecutive_dots(self, verifier):
        valid, reason = verifier._validate_syntax("test..test@example.com")
        assert valid is False

    def test_invalid_email_empty(self, verifier):
        valid, reason = verifier._validate_syntax("")
        assert valid is False


class TestDisposableCheck:
    def test_disposable_domain_detected(self, verifier):
        assert verifier._is_disposable("mailinator.com") is True
        assert verifier._is_disposable("tempmail.com") is True

    def test_normal_domain_not_disposable(self, verifier):
        assert verifier._is_disposable("gmail.com") is False
        assert verifier._is_disposable("company.com") is False


class TestMXLookup:
    def test_valid_domain_has_mx(self, verifier):
        # Google's domain should have MX records
        mx_records = verifier._get_mx_records("google.com")
        assert len(mx_records) > 0

    def test_invalid_domain_no_mx(self, verifier):
        # Nonsense domain shouldn't have MX
        mx_records = verifier._get_mx_records("thisisnotarealdomain12345.com")
        assert len(mx_records) == 0


@pytest.mark.asyncio
async def test_verify_valid_email(verifier):
    # Test with a real domain (gmail)
    result = await verifier.verify("test@gmail.com")
    assert result.status == VerificationStatus.VALID
    assert result.is_deliverable is True


@pytest.mark.asyncio
async def test_verify_invalid_syntax():
    verifier = EmailVerifier()
    result = await verifier.verify("not-an-email")
    assert result.status == VerificationStatus.INVALID
    assert result.is_deliverable is False


@pytest.mark.asyncio
async def test_verify_disposable_email():
    verifier = EmailVerifier()
    result = await verifier.verify("test@mailinator.com")
    assert result.status == VerificationStatus.DISPOSABLE
    assert result.is_risky is True


@pytest.mark.asyncio
async def test_verify_no_mx_domain():
    verifier = EmailVerifier()
    result = await verifier.verify("test@thisisnotarealdomain12345.com")
    assert result.status == VerificationStatus.NO_MX


@pytest.mark.asyncio
async def test_verify_batch():
    verifier = EmailVerifier()
    emails = ["test@gmail.com", "bad-email", "test@mailinator.com"]
    results = await verifier.verify_batch(emails)

    assert len(results) == 3
    # First should be valid, second invalid, third disposable
    assert results[0].status == VerificationStatus.VALID
    assert results[1].status == VerificationStatus.INVALID
    assert results[2].status == VerificationStatus.DISPOSABLE


def test_filter_valid_emails():
    from src.email_verifier import VerificationResult

    results = [
        VerificationResult("good@test.com", VerificationStatus.VALID, True, False),
        VerificationResult("bad@test.com", VerificationStatus.INVALID, False, False),
        VerificationResult("risky@test.com", VerificationStatus.CATCH_ALL, False, True),
    ]

    valid = filter_valid_emails(results)
    assert valid == ["good@test.com"]

    valid_with_risky = filter_valid_emails(results, include_risky=True)
    assert "good@test.com" in valid_with_risky
    assert "risky@test.com" in valid_with_risky
