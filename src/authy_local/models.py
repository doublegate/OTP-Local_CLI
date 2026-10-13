"""Validate external scope and code values before use."""

import re
from dataclasses import dataclass, field

from .errors import AppError


@dataclass(frozen=True)
class Scope:
    item: str = field(repr=False)
    account: str = field(repr=False)
    vault: str = field(repr=False)

    def __post_init__(self):
        # Account IDs use the conservative baseline; live compatibility is gated.
        if any(
            re.fullmatch(r"[A-Za-z0-9]{26}", value) is None
            for value in (self.item, self.account, self.vault)
        ):
            raise AppError(2)


def parse_code(raw: bytes) -> str:
    if re.fullmatch(rb"(?:[0-9]{6}|[0-9]{8})(?:\r?\n)?", raw) is None:
        raise AppError(5)
    return raw.rstrip(b"\r\n").decode("ascii")
