#!/usr/bin/env python3
"""
Format (pretty-print) a JSON file in a streaming way.

This is primarily intended for CPG JSON exports (which can be very large and are often written as
one long line), but it works for any JSON.

Why streaming?
  - Avoids loading the whole JSON document into memory.
  - Keeps key ordering and values exactly as-is (we only change whitespace outside strings).

Examples:
  python3 scripts/format_cpg_json.py /tmp/cpg.json
  python3 scripts/format_cpg_json.py /tmp/cpg.json -o /tmp/cpg.pretty.json
  python3 scripts/format_cpg_json.py /tmp/cpg.json --in-place
  cat /tmp/cpg.json | python3 scripts/format_cpg_json.py - -o /tmp/cpg.pretty.json
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import IO


@dataclass
class _Container:
    opener: str  # "{" or "["
    empty: bool = True


def _indent_cache(indent_size: int) -> list[str]:
    # cache[level] -> indentation string for that level
    return [""]


def _get_indent(cache: list[str], level: int, indent_size: int) -> str:
    while len(cache) <= level:
        cache.append(cache[-1] + (" " * indent_size))
    return cache[level]


def format_json_stream(
    in_fp: IO[str],
    out_fp: IO[str],
    *,
    indent_size: int = 2,
    chunk_size: int = 64 * 1024,
) -> None:
    in_string = False
    escape = False
    need_newline_and_indent = False
    stack: list[_Container] = []

    cache = _indent_cache(indent_size)

    def write(text: str) -> None:
        out_fp.write(text)

    def maybe_emit_newline_and_indent() -> None:
        nonlocal need_newline_and_indent
        if not need_newline_and_indent:
            return
        need_newline_and_indent = False
        write("\n")
        write(_get_indent(cache, len(stack), indent_size))

    def mark_current_container_non_empty_if_needed() -> None:
        if stack and stack[-1].empty:
            stack[-1].empty = False

    while True:
        chunk = in_fp.read(chunk_size)
        if not chunk:
            break

        for ch in chunk:
            if in_string:
                write(ch)
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue

            # Outside strings: we canonicalize whitespace (i.e., ignore it completely).
            if ch in " \t\r\n":
                continue

            if ch == '"':
                maybe_emit_newline_and_indent()
                mark_current_container_non_empty_if_needed()
                in_string = True
                write(ch)
                continue

            if ch in "{[":
                maybe_emit_newline_and_indent()
                mark_current_container_non_empty_if_needed()
                write(ch)
                stack.append(_Container(opener=ch, empty=True))
                need_newline_and_indent = True
                continue

            if ch in "}]":
                if not stack:
                    raise ValueError(f"Unexpected closing bracket {ch!r} (no open containers)")

                container = stack[-1]
                if container.opener == "{" and ch != "}":
                    raise ValueError(
                        f"Mismatched closing bracket {ch!r} for opener {container.opener!r}"
                    )
                if container.opener == "[" and ch != "]":
                    raise ValueError(
                        f"Mismatched closing bracket {ch!r} for opener {container.opener!r}"
                    )

                stack.pop()

                if container.empty:
                    # If we just opened the container and it turns out to be empty, keep it compact:
                    #   {} / [] instead of
                    #   {
                    #   }
                    need_newline_and_indent = False
                    write(ch)
                else:
                    # Close on its own line at the parent's indentation level.
                    need_newline_and_indent = False
                    write("\n")
                    write(_get_indent(cache, len(stack), indent_size))
                    write(ch)
                continue

            if ch == ",":
                write(",")
                need_newline_and_indent = True
                continue

            if ch == ":":
                write(": ")
                continue

            # Literals / numbers / minus sign etc.
            maybe_emit_newline_and_indent()
            mark_current_container_non_empty_if_needed()
            write(ch)

    if in_string:
        raise ValueError("Unterminated string (reached EOF while inside a JSON string)")
    if stack:
        raise ValueError(
            "Unclosed container(s) at EOF: " + "".join(c.opener for c in stack)
        )

    write("\n")


def _open_in(path: str) -> IO[str]:
    if path == "-":
        return sys.stdin
    return open(path, "r", encoding="utf-8")


def _open_out(path: str) -> IO[str]:
    if path == "-":
        return sys.stdout
    return open(path, "w", encoding="utf-8", newline="\n")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Pretty-print a JSON file (streaming, memory-friendly).",
    )
    parser.add_argument(
        "input",
        help="Input JSON file path, or '-' for stdin.",
    )
    parser.add_argument(
        "-o",
        "--out",
        help="Output file path. Defaults to '<input>.pretty.json' (or stdout if input is '-').",
        default=None,
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="Indentation size (spaces). Default: 2",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite the input file in-place (ignored if input is '-').",
    )
    args = parser.parse_args(argv)

    if args.indent < 0:
        parser.error("--indent must be >= 0")

    if args.input == "-" and args.in_place:
        parser.error("--in-place cannot be used with stdin ('-')")

    if args.in_place:
        in_path = Path(args.input)
        tmp_dir = in_path.parent
        fd, tmp_path_str = tempfile.mkstemp(
            prefix=in_path.name + ".",
            suffix=".pretty.tmp",
            dir=str(tmp_dir),
            text=True,
        )
        os.close(fd)
        tmp_path = Path(tmp_path_str)
        try:
            with _open_in(args.input) as in_fp, _open_out(str(tmp_path)) as out_fp:
                format_json_stream(in_fp, out_fp, indent_size=args.indent)
            tmp_path.replace(in_path)
        finally:
            # If something failed before replace(), ensure temp file is removed.
            if tmp_path.exists() and tmp_path != in_path:
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
        return 0

    out_path: str
    if args.out is not None:
        out_path = args.out
    elif args.input == "-":
        out_path = "-"
    else:
        out_path = args.input + ".pretty.json"

    with _open_in(args.input) as in_fp, _open_out(out_path) as out_fp:
        format_json_stream(in_fp, out_fp, indent_size=args.indent)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

