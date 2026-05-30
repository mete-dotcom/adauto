"""
adauto — First-run gate: Terms of Service + key recovery helper.
Self-contained. State stored in ~/.adauto/accepted_tos.
"""
from __future__ import annotations
import sys
from pathlib import Path

TOS_VERSION  = "1.0"
_TOS_FILE    = Path.home() / ".adauto" / "accepted_tos"
_TOS_URL     = "https://adauto.massiron.com/terms"
_RECOVER_URL = "https://adauto.massiron.com/recover"

TOS_TEXT = f"""
┌─────────────────────────────────────────────────────────┐
│              adauto  ·  Terms of Use v{TOS_VERSION}              │
├─────────────────────────────────────────────────────────┤
│  adauto automates developer marketing with your         │
│  approval. By using adauto you agree:                   │
│                                                         │
│  1. You are responsible for all content you approve     │
│     and publish through adauto.                         │
│  2. Do not use adauto to post spam, misleading, or      │
│     harmful content.                                    │
│  3. Platform terms (Reddit, X, dev.to) still apply.    │
│  4. Full terms: {_TOS_URL:<41}│
└─────────────────────────────────────────────────────────┘
Type  yes  to accept and continue, or  no  to exit.
"""

def tos_accepted() -> bool:
    return _TOS_FILE.exists() and _TOS_FILE.read_text().strip() == TOS_VERSION

def accept_tos() -> None:
    _TOS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TOS_FILE.write_text(TOS_VERSION)

def ensure_tos(silent: bool = False) -> None:
    if tos_accepted():
        return
    if silent or not sys.stdout.isatty():
        return
    print(TOS_TEXT)
    try:
        answer = input(">>> ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "no"
    if answer != "yes":
        print("Exiting. You must accept the terms to use adauto.")
        sys.exit(0)
    accept_tos()
    print("✓ Terms accepted.\n")

def print_recovery_hint() -> None:
    print(f"\n  Lost your license key?  →  {_RECOVER_URL}")
    print("  Your purchase email has the key. Check spam too.\n")
