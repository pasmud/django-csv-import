from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Issue:
    """An input problem, optionally located by physical line and CSV header."""

    code: str
    message: str
    line: int | None = None
    column: str | None = None
