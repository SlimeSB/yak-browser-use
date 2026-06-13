"""Parameter management CLI — replaces the old credential/auth system.

Stores persistent key-value parameters in a plain JSON file (~/.ybu/params.json).
"""

from __future__ import annotations

import sys

from params.manager import ParamManager, list_param_keys, delete_param


def _cmd_param_set(key: str, value: str) -> None:
    """Store a persistent parameter value.

    Args:
        key: Parameter key name.
        value: Parameter value.
    """
    mgr = ParamManager()
    mgr.set(key, value)
    print(f"\u2713 Parameter '{key}' saved to {mgr._path}")
    print(f"  (can also set via environment variable: YBU_PARAM_{key.upper()}={value})")


def _cmd_param_list() -> None:
    """List all stored parameter keys."""
    keys = list_param_keys()
    if not keys:
        print("(no stored parameters)")
        print("Use 'ybu param set <key> <value>' to add a parameter")
    else:
        print(f"Stored parameters ({len(keys)}):")
        for k in keys:
            print(f"  - {k}")


def _cmd_param_delete(key: str) -> None:
    """Delete a parameter with user confirmation.

    Args:
        key: Parameter key to delete.
    """
    keys = list_param_keys()
    if key not in keys:
        print(f"Parameter '{key}' does not exist — nothing to delete")
        return

    answer = input(f"Delete parameter '{key}'? [y/N]: ").strip().lower()
    if answer in ("y", "yes"):
        delete_param(key)
        print(f"\u2713 Parameter '{key}' deleted")
    else:
        print("Cancelled")
