# src/email_verifier.py
"""
Custom email verification without paid APIs.

Verification steps:
1. Syntax validation - Check email format
2. MX record lookup - Verify domain has mail servers
3. SMTP verification - Check if mailbox exists (optional, can be slow/blocked)

No API keys required!
"""
import asyncio
import re
import socket
import dns.resolver
import smtplib
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from email.utils import parseaddr


class VerificationStatus(Enum):
    VALID = "valid"           # Email is likely deliverable
    INVALID = "invalid"       # Email doesn't exist or bad format
    CATCH_ALL = "catch_all"   # Domain accepts all emails (risky)
    UNKNOWN = "unknown"       # Could not determine
    DISPOSABLE = "disposable" # Temporary email domain
    NO_MX = "no_mx"           # Domain has no mail servers


@dataclass
class VerificationResult:
    email: str
    status: VerificationStatus
    is_deliverable: bool
    is_risky: bool
    reason: Optional[str] = None
    checks: Optional[dict] = None


# Common disposable email domains
DISPOSABLE_DOMAINS = {
    "tempmail.com", "throwaway.email", "guerrillamail.com", "mailinator.com",
    "10minutemail.com", "fakeinbox.com", "trashmail.com", "tempinbox.com",
    "temp-mail.org", "throwawaymail.com", "getnada.com", "maildrop.cc",
    "yopmail.com", "sharklasers.com", "spam4.me", "dispostable.com",
    "mailnesia.com", "tempail.com", "fakemailgenerator.com", "mohmal.com",
}


class EmailVerifier:
    """Verifies email addresses using DNS and SMTP checks."""

    def __init__(
        self,
        verify_smtp: bool = False,  # SMTP check is slow and often blocked
        timeout: int = 10,
        from_email: str = "verify@example.com"
    ):
        self.verify_smtp = verify_smtp
        self.timeout = timeout
        self.from_email = from_email

    def _validate_syntax(self, email: str) -> tuple[bool, str]:
        """Check if email has valid syntax."""
        # Basic regex for email validation
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

        if not email or not isinstance(email, str):
            return False, "Empty or invalid email"

        email = email.strip().lower()

        # Check with parseaddr
        name, addr = parseaddr(email)
        if not addr:
            return False, "Could not parse email address"

        if not re.match(pattern, email):
            return False, "Invalid email format"

        # Check for common typos
        if ".." in email:
            return False, "Contains consecutive dots"

        if email.startswith(".") or email.endswith("."):
            return False, "Starts or ends with dot"

        return True, "Valid syntax"

    def _get_domain(self, email: str) -> str:
        """Extract domain from email."""
        return email.strip().lower().split("@")[1]

    def _is_disposable(self, domain: str) -> bool:
        """Check if domain is a known disposable email provider."""
        return domain.lower() in DISPOSABLE_DOMAINS

    def _get_mx_records(self, domain: str) -> list[str]:
        """Get MX records for a domain."""
        try:
            mx_records = dns.resolver.resolve(domain, 'MX')
            return sorted(
                [(r.preference, str(r.exchange).rstrip('.')) for r in mx_records],
                key=lambda x: x[0]
            )
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
            return []
        except Exception:
            return []

    def _verify_smtp(self, email: str, mx_host: str) -> tuple[bool, str]:
        """
        Verify email exists via SMTP.
        Note: Many servers block this or return false positives.
        """
        try:
            # Connect to SMTP server
            smtp = smtplib.SMTP(timeout=self.timeout)
            smtp.connect(mx_host)
            smtp.helo("verify.local")
            smtp.mail(self.from_email)

            # Try RCPT TO
            code, message = smtp.rcpt(email)
            smtp.quit()

            if code == 250:
                return True, "SMTP accepted recipient"
            elif code == 550:
                return False, "SMTP rejected recipient"
            else:
                return False, f"SMTP returned code {code}"

        except smtplib.SMTPServerDisconnected:
            return False, "SMTP server disconnected"
        except smtplib.SMTPConnectError:
            return False, "Could not connect to SMTP server"
        except socket.timeout:
            return False, "SMTP connection timed out"
        except Exception as e:
            return False, f"SMTP error: {str(e)}"

    async def verify(self, email: str) -> VerificationResult:
        """
        Verify a single email address.

        Checks:
        1. Syntax validation
        2. Disposable domain check
        3. MX record lookup
        4. SMTP verification (optional)
        """
        checks = {}

        # Step 1: Syntax validation
        syntax_valid, syntax_reason = self._validate_syntax(email)
        checks["syntax"] = {"valid": syntax_valid, "reason": syntax_reason}

        if not syntax_valid:
            return VerificationResult(
                email=email,
                status=VerificationStatus.INVALID,
                is_deliverable=False,
                is_risky=False,
                reason=syntax_reason,
                checks=checks
            )

        email = email.strip().lower()
        domain = self._get_domain(email)

        # Step 2: Check for disposable domain
        is_disposable = self._is_disposable(domain)
        checks["disposable"] = {"is_disposable": is_disposable}

        if is_disposable:
            return VerificationResult(
                email=email,
                status=VerificationStatus.DISPOSABLE,
                is_deliverable=False,
                is_risky=True,
                reason="Disposable email domain",
                checks=checks
            )

        # Step 3: MX record lookup (run in thread pool to avoid blocking)
        loop = asyncio.get_event_loop()
        mx_records = await loop.run_in_executor(None, self._get_mx_records, domain)
        checks["mx"] = {"records": [r[1] for r in mx_records] if mx_records else []}

        if not mx_records:
            return VerificationResult(
                email=email,
                status=VerificationStatus.NO_MX,
                is_deliverable=False,
                is_risky=False,
                reason="Domain has no MX records",
                checks=checks
            )

        # Step 4: SMTP verification (optional)
        if self.verify_smtp and mx_records:
            mx_host = mx_records[0][1]  # Use primary MX
            smtp_valid, smtp_reason = await loop.run_in_executor(
                None, self._verify_smtp, email, mx_host
            )
            checks["smtp"] = {"valid": smtp_valid, "reason": smtp_reason}

            if not smtp_valid and "rejected" in smtp_reason.lower():
                return VerificationResult(
                    email=email,
                    status=VerificationStatus.INVALID,
                    is_deliverable=False,
                    is_risky=False,
                    reason=smtp_reason,
                    checks=checks
                )

        # If we got here, email is likely valid
        return VerificationResult(
            email=email,
            status=VerificationStatus.VALID,
            is_deliverable=True,
            is_risky=False,
            reason="Passed all checks",
            checks=checks
        )

    async def verify_batch(
        self,
        emails: list[str],
        concurrency: int = 10
    ) -> list[VerificationResult]:
        """Verify multiple emails with concurrency control."""
        semaphore = asyncio.Semaphore(concurrency)
        results = []

        async def verify_one(email: str) -> VerificationResult:
            async with semaphore:
                try:
                    return await self.verify(email)
                except Exception as e:
                    return VerificationResult(
                        email=email,
                        status=VerificationStatus.UNKNOWN,
                        is_deliverable=False,
                        is_risky=True,
                        reason=str(e)
                    )

        tasks = [verify_one(email) for email in emails]
        results = await asyncio.gather(*tasks)
        return list(results)


def filter_valid_emails(
    results: list[VerificationResult],
    include_risky: bool = False
) -> list[str]:
    """
    Filter verification results to get valid emails.

    Args:
        results: List of verification results
        include_risky: Whether to include risky emails (catch-all, unknown)

    Returns:
        List of valid email addresses
    """
    valid = []
    for result in results:
        if result.is_deliverable:
            valid.append(result.email)
        elif include_risky and result.status in (
            VerificationStatus.CATCH_ALL,
            VerificationStatus.UNKNOWN
        ):
            valid.append(result.email)
    return valid
