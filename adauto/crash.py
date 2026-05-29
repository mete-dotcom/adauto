"""
adauto crash reporter — never crash silently, never show raw tracebacks.

Usage:
    from .crash import guard, retry, log

    @retry(max=3, delay=2.0, on=(requests.exceptions.ConnectionError,))
    def risky_call(): ...

    with guard("posting to reddit"):
        poster.post(...)

    log.warning("something odd happened")
"""
from __future__ import annotations

import functools
import json
import logging
import logging.handlers
import os
import sys
import time
import traceback
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Tuple, Type

# ── directories ───────────────────────────────────────────────────────────────

_CONFIG_DIR = Path.home() / ".adauto"
_CRASH_DIR  = _CONFIG_DIR / "crashes"
_LOG_FILE   = _CONFIG_DIR / "adauto.log"

_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
_CRASH_DIR.mkdir(parents=True, exist_ok=True)

# ── logging ───────────────────────────────────────────────────────────────────

def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("adauto")
    if logger.handlers:           # already initialised in this process
        return logger
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler — 2 MB × 3 backups, never crashes on PermissionError
    try:
        fh = logging.handlers.RotatingFileHandler(
            _LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3,
            encoding="utf-8",
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass  # log file unavailable — continue without it

    return logger


log: logging.Logger = _setup_logger()

# ── crash report writer ───────────────────────────────────────────────────────

def write_crash_report(
    exc: BaseException,
    context: str = "",
    extra: dict | None = None,
) -> Path:
    """Write a JSON crash report to ~/.adauto/crashes/ and return its path."""
    ts   = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    uid  = uuid.uuid4().hex[:8]
    path = _CRASH_DIR / f"{ts}_{uid}.json"

    report = {
        "version":    1,
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "context":    context,
        "exception":  type(exc).__name__,
        "message":    str(exc),
        "traceback":  traceback.format_exc(),
        "extra":      extra or {},
        "python":     sys.version,
        "pid":        os.getpid(),
    }

    try:
        path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        log.error("crash report written: %s", path)
    except Exception:
        pass  # truly last resort — can't even write the crash report

    return path


# ── friendly terminal output ──────────────────────────────────────────────────

_FRIENDLY: dict[str, str] = {
    "ConnectionError":   "Could not reach the server. Is deepstrain running on :8765?",
    "Timeout":           "Request timed out. deepstrain may be busy — retrying later.",
    "ConnectionRefused": "Connection refused. Start deepstrain first: `deepstrain serve`",
    "JSONDecodeError":   "Received an unexpected response (not valid JSON). deepstrain may still be starting up.",
    "PermissionError":   "Permission denied. Check that ~/.adauto/ is writable.",
    "FileNotFoundError": "A required file was not found. Your config may be incomplete.",
    "KeyboardInterrupt": "Interrupted.",
}

def friendly_message(exc: BaseException) -> str:
    """Return a human-readable error message — no traceback, no noise."""
    name = type(exc).__name__
    for key, msg in _FRIENDLY.items():
        if key.lower() in name.lower() or key.lower() in str(exc).lower():
            return msg
    return f"Something went wrong: {name}: {exc}"


def print_error(exc: BaseException, context: str = "", *, crash_path: Path | None = None) -> None:
    """Print a friendly error message to stderr."""
    msg = friendly_message(exc)
    header = f"[adauto] Error{' in ' + context if context else ''}: {msg}"
    print(header, file=sys.stderr)
    if crash_path and crash_path.exists():
        print(f"[adauto] Full details saved to: {crash_path}", file=sys.stderr)
    log.error("error in %r: %s: %s", context or "unknown", type(exc).__name__, exc)


# ── guard context manager ─────────────────────────────────────────────────────

@contextmanager
def guard(context: str = "", *, fatal: bool = False, extra: dict | None = None):
    """
    Context manager that catches any exception, writes a crash report,
    prints a friendly message, and either re-raises (fatal=True) or swallows.

    with guard("posting to reddit"):
        poster.post(camp, plat, post)
    """
    try:
        yield
    except KeyboardInterrupt:
        print("\n[adauto] Interrupted.", file=sys.stderr)
        raise
    except SystemExit:
        raise
    except BaseException as exc:
        crash_path = write_crash_report(exc, context=context, extra=extra)
        print_error(exc, context=context, crash_path=crash_path)
        if fatal:
            raise


# ── retry decorator ───────────────────────────────────────────────────────────

_TRANSIENT: tuple[type, ...] = ()

try:
    import requests
    _TRANSIENT = (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.ChunkedEncodingError,
    )
except ImportError:
    pass


def retry(
    max: int = 3,
    delay: float = 2.0,
    backoff: float = 2.0,
    on: Tuple[Type[BaseException], ...] | None = None,
    label: str = "",
) -> Callable:
    """
    Retry decorator for transient failures.

    @retry(max=3, delay=2.0)
    def call_deepstrain(): ...

    - Retries on `on` exceptions (default: common network errors).
    - Exponential back-off: delay, delay*backoff, delay*backoff², …
    - Logs each retry attempt.
    - Raises the last exception after `max` attempts.
    """
    catch = on if on is not None else _TRANSIENT
    if not catch:
        catch = (OSError, IOError)

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            wait = delay
            last_exc: BaseException | None = None
            for attempt in range(1, max + 1):
                try:
                    return fn(*args, **kwargs)
                except catch as exc:   # type: ignore[misc]
                    last_exc = exc
                    name = label or fn.__name__
                    if attempt < max:
                        log.warning(
                            "[retry] %s attempt %d/%d failed: %s — waiting %.1fs",
                            name, attempt, max, exc, wait,
                        )
                        print(
                            f"[adauto] {name} failed (attempt {attempt}/{max}), "
                            f"retrying in {wait:.0f}s… ({exc})",
                            file=sys.stderr,
                        )
                        time.sleep(wait)
                        wait *= backoff
                    else:
                        log.error(
                            "[retry] %s gave up after %d attempts: %s",
                            name, max, exc,
                        )
            raise last_exc  # type: ignore[misc]
        return wrapper
    return decorator


# ── top-level CLI guard ───────────────────────────────────────────────────────

def run_cli(fn: Callable, *args, **kwargs) -> None:
    """
    Run a Click CLI entry point with a top-level catch-all.
    Never shows a Python traceback to the user.
    """
    try:
        fn(*args, **kwargs)
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print("\n[adauto] Interrupted.", file=sys.stderr)
        sys.exit(130)
    except BaseException as exc:
        crash_path = write_crash_report(exc, context="cli")
        print_error(exc, context="cli top-level", crash_path=crash_path)
        sys.exit(1)
