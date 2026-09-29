from __future__ import annotations

import re
from dataclasses import asdict, dataclass

_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f-]{27,}\b", re.IGNORECASE)
_TIMESTAMP = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b"
)
_PORT = re.compile(r"(?<=:)(\d{4,5})(?=/|\b)")
_LINE_NUMBER = re.compile(r"(?<=\.py:)(\d+)(?=\b)")
_TOKEN = re.compile(r"\b(?:Bearer\s+)?(?:eyJ[a-zA-Z0-9._-]+|(?:token|session)[-_:= ]+[a-zA-Z0-9._-]+)\b", re.I)
_OBSERVED_STATUS = re.compile(r"(?:received\s+|->\s*)(\d{3})", re.I)
_FALLBACK_STATUS = re.compile(r"(?:status(?:_code)?\s*[=:]?|HTTP\s*)(\d{3})", re.I)
_ENDPOINT = re.compile(r"/(?:api/)?[a-zA-Z0-9_./{}-]+")
_EXCEPTION = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception))\b")


@dataclass(frozen=True)
class Fingerprint:
    service: str
    endpoint: str
    status: str
    exception: str

    def key(self) -> str:
        return "|".join((self.service, self.endpoint, self.status, self.exception))

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def normalize_failure_text(text: str) -> str:
    """Remove common run-specific values while retaining diagnostic structure."""
    text = _TIMESTAMP.sub("<timestamp>", text)
    text = _UUID.sub("<uuid>", text)
    text = _TOKEN.sub("<token>", text)
    text = _PORT.sub("<port>", text)
    text = _LINE_NUMBER.sub("<line>", text)
    text = re.sub(r"\b(?:request|order|user|build)[-_ ]?id\s*[=: ]\s*[\w-]+", "<id>", text, flags=re.I)
    return text


def fingerprint_failure(
    error_message: str,
    stack_trace: str = "",
    *,
    endpoint: str | None = None,
    status: int | str | None = None,
) -> Fingerprint:
    text = normalize_failure_text(f"{error_message}\n{stack_trace}")
    endpoint_match = _ENDPOINT.search(endpoint or text)
    normalized_endpoint = endpoint_match.group(0) if endpoint_match else "unknown"
    normalized_endpoint = "/" + normalized_endpoint.lstrip("/")

    status_match = _OBSERVED_STATUS.search(text) or _FALLBACK_STATUS.search(text)
    normalized_status = str(status) if status is not None else (
        str(status_match.group(1)) if status_match else "unknown"
    )
    exception_match = _EXCEPTION.search(error_message)
    exception = exception_match.group(1) if exception_match else "AssertionError"

    service = {
        "/api/checkout": "checkout",
        "/api/profile": "auth",
        "/api/cart/total": "cart",
    }.get(normalized_endpoint, normalized_endpoint.split("/")[1] if normalized_endpoint.count("/") > 1 else "unknown")

    return Fingerprint(service, normalized_endpoint, normalized_status, exception)
