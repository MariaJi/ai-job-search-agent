class VerificationStatus:
    # Missing or unsupported evidence must never imply successful verification.
    UNVERIFIED = "unverified"
    PENDING = "pending"
    # Description was already complete, so source verification was skipped.
    # This is intentionally distinct from VERIFIED and does not certify a score.
    NOT_NEEDED = "not_needed"
    NOT_ATTEMPTED = "not_attempted"
    NOT_FOUND = "not_found"
    FAILED = "failed"
    SERVICE_ERROR = "service_error"
    VERIFIED = "verified"

    @classmethod
    def normalize(cls, value: object) -> str:
        """Accept exact supported statuses; do not infer or coerce verification."""
        supported = (
            cls.UNVERIFIED, cls.PENDING, cls.NOT_NEEDED, cls.NOT_ATTEMPTED,
            cls.NOT_FOUND, cls.FAILED, cls.SERVICE_ERROR, cls.VERIFIED,
        )
        return value if isinstance(value, str) and value in supported else cls.UNVERIFIED


class AnalysisType:
    PRELIMINARY = "preliminary"
    VERIFIED = "verified"
