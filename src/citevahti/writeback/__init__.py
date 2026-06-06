"""Guarded, optional Zotero write-back (step 9).

Write-back is opt-in and separate from CiteVahti state: every stateful feature
works without it. Every write defaults to dry-run, requires an explicit
confirmation token bound to the exact pending diff, and never silently falls back
from the local add-on to the Web API. Confirmed writes append an audit event.
"""

from .backend import (
    FakeWriteBackend,
    UnavailableBackend,
    WriteBackend,
    WriteUnavailable,
    make_backend,
)
from .layer import WriteLayer
from .service import WritebackService
from .transaction import TransactionError, TransactionService
from .webapi import WebApiWriteBackend

__all__ = [
    "WriteLayer",
    "WritebackService",
    "TransactionService",
    "TransactionError",
    "WriteBackend",
    "FakeWriteBackend",
    "UnavailableBackend",
    "WebApiWriteBackend",
    "WriteUnavailable",
    "make_backend",
]
