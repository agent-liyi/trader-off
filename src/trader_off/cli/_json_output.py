"""Shared helper for --json output flag across CLI modules (FR-0100).

When --json is enabled, all normal stdout output is suppressed and only a
final JSON blob is written to stdout just before the program exits.

Error codes are mapped through an optional ``error_messages`` dict. If not
provided, a default set of messages is used.

Usage inside a CLI main()::

    def main(argv=None):
        parser = _build_parser()
        parser.add_argument("--json", action="store_true", help="Output JSON")
        args = parser.parse_args(argv)

        if args.json:
            return _json_wrap(lambda: _run(args), error_messages={2: "...", 4: "..."})
        return _run(args)
"""

from __future__ import annotations

import io
import json
import sys
from collections.abc import Callable

_DEFAULT_ERROR_MESSAGES: dict[int, str] = {
    1: "Unknown error",
    2: "CLI argument error",
    3: "Insufficient data",
    4: "Configuration error",
    5: "Execution failure",
}


def _json_wrap(
    run_fn: Callable[[], int],
    error_messages: dict[int, str] | None = None,
) -> int:
    """Execute ``run_fn`` with stdout suppressed; emit JSON on exit.

    All normal print/write to stdout is captured and discarded. Only the
    final JSON status blob is written to the *real* stdout.

    ``SystemExit`` is re-raised so argparse error messages still reach the
    caller (when --json is set, argparse prints to stderr, which is fine).

    Args:
        run_fn: A zero-argument callable that returns an exit code.
        error_messages: Optional mapping of exit codes to human-readable
            messages.  Falls back to ``_DEFAULT_ERROR_MESSAGES``.

    Returns:
        The exit code originally returned by ``run_fn``.
    """
    real_stdout = sys.stdout
    sys.stdout = io.StringIO()

    try:
        code = run_fn()
        _emit_json(real_stdout, code, error_messages or _DEFAULT_ERROR_MESSAGES)
        return code
    except SystemExit:
        raise
    except Exception as exc:
        _emit_json(real_stdout, 1, {1: str(exc)})
        return 1
    finally:
        sys.stdout = real_stdout


def _emit_json(
    stream,
    code: int,
    error_messages: dict[int, str],
) -> None:
    """Write a JSON status blob to *stream*.

    ``stream`` is normally the *real* ``sys.stdout`` that was saved before
    the redirect.

    Args:
        stream: The writeable stream for JSON output.
        code: Exit code (0 = success).
        error_messages: Mapping from exit codes to message strings.
    """
    if code == 0:
        payload = json.dumps({"status": "ok", "data": {}})
    else:
        msg = error_messages.get(code, f"CLI exited with code {code}")
        payload = json.dumps({"status": "error", "code": code, "message": msg})
    stream.write(payload)
