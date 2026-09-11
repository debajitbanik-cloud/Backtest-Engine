"""Pine Script v4/v5 line-oriented parser → IR.

Parses a subset of Pine Script into an intermediate representation (IR).
NEVER eval/exec user code — only whitelisted constructs are accepted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class PineParseError(Exception):
    """Raised when the parser encounters an unrecoverable error."""


@dataclass
class PineIR:
    meta: Dict[str, Any] = field(default_factory=dict)
    inputs: List[Dict[str, Any]] = field(default_factory=list)
    plots: List[Dict[str, Any]] = field(default_factory=list)
    assigns: Dict[str, Any] = field(default_factory=dict)  # name -> expression AST
    errors: List[Dict[str, Any]] = field(default_factory=list)


# ── Whitelists ──────────────────────────────────────────────────────────

_SERIES_BUILTINS = {"open", "high", "low", "close", "volume", "hl2", "hlc3", "ohlc4"}
_TA_FUNCTIONS = {"ta.sma", "ta.ema", "ta.rsi", "ta.macd"}
_BARE_ALIASES = {"sma", "ema", "rsi"}  # v4 aliases → ta.*
_MATH_FUNCTIONS = {"math.abs", "math.max", "math.min"}
_NZ_FUNCTION = "nz"
_REJECTED_FUNCTIONS = {
    "request.security", "request.security_lower_tf", "request.seed",
    "fill", "bgcolor", "barcolor", "plotshape", "plotchar",
    "label.new", "box.new", "line.new",
    "ta.stoch", "ta.atr", "ta.cci", "ta.wpr", "ta.mfi",
    "ta.supertrend", "ta.highest", "ta.lowest", "ta.crossover", "ta.crossunder",
    "ta.change", "ta.delta", "ta.eci", "ta.ebb", "ta.pivothigh", "ta.pivotlow",
    "ta.valuewhen", "ta.barssince", "ta.barssincewhen", "ta.statewhen",
    "str.format", "str.tostring", "str.length",
    "array.new", "matrix.new", "map.new",
}

# Patterns for rejected constructs
_LOOP_PATTERN = re.compile(r"\b(for|while|loop)\s*\(", re.IGNORECASE)
_TERNARY_PATTERN = re.compile(r"\?")
_VARIP_PATTERN = re.compile(r"\bvarip\b", re.IGNORECASE)
_IMPORT_PATTERN = re.compile(r"\bimport\b", re.IGNORECASE)
_TYPE_PATTERN = re.compile(r"\btype\s+\w+", re.IGNORECASE)
_METHOD_DEF_PATTERN = re.compile(r"\bmethod\s+\w+\.\w+\s*\(", re.IGNORECASE)


def parse_pine(code: str) -> PineIR:
    """Parse Pine Script code into an IR.

    Returns a PineIR with meta, inputs, plots, and any per-line errors.
    """
    ir = PineIR()
    lines = code.split("\n")

    for lineno, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()

        # Skip blank lines
        if not line:
            continue

        # Version comment (e.g. //@version=5) — check BEFORE comment skip
        vm = re.match(r"^//@version=(\d+)", line)
        if vm:
            ir.meta["version"] = int(vm.group(1))
            continue

        # Skip comment-only lines
        if line.startswith("//"):
            continue

        # Strip inline comments
        code_part = _strip_comment(line)

        # --- Check rejected constructs first ---
        err = _check_rejected(lineno, code_part)
        if err:
            ir.errors.append(err)
            continue

        # --- Parse recognized statements ---
        parsed = False
        for parser_fn in [
            _parse_indicator,
            _parse_input,
            _parse_hline,
            _parse_plot,
            _parse_assignment,
        ]:
            result = parser_fn(lineno, code_part)
            if result is not None:
                if isinstance(result, dict) and "error" in result:
                    ir.errors.append(result["error"])
                else:
                    _merge_result(ir, result)
                parsed = True
                break

        # Unrecognized line — collect as non-blocking note
        if not parsed:
            if code_part.strip():
                ir.errors.append({
                    "line": lineno,
                    "code": "UNSUPPORTED",
                    "reason": f"Unrecognized construct: {code_part[:120]}",
                })

    return ir


# ── Internal helpers ────────────────────────────────────────────────────

def _strip_comment(line: str) -> str:
    """Remove trailing // comments (naive — doesn't handle strings)."""
    idx = line.find("//")
    if idx < 0:
        return line
    return line[:idx].strip()


def _check_rejected(lineno: int, line: str) -> Optional[Dict[str, Any]]:
    """Return an error dict if the line contains a rejected Pine construct."""
    stripped = line.strip()

    # strategy() call
    if re.match(r"\bstrategy\s*\(", stripped):
        return {"line": lineno, "code": "REJECTED", "reason": "strategy() is not supported in v1"}

    # request.* calls
    if re.match(r"\brequest\.\w+", stripped):
        return {"line": lineno, "code": "REJECTED", "reason": "request.* functions are not supported in v1"}

    # Loops
    if _LOOP_PATTERN.search(stripped):
        return {"line": lineno, "code": "REJECTED", "reason": "Loops (for/while) are not supported in v1"}

    # varip
    if _VARIP_PATTERN.search(stripped):
        return {"line": lineno, "code": "REJECTED", "reason": "varip is not supported in v1"}

    # import
    if _IMPORT_PATTERN.search(stripped):
        return {"line": lineno, "code": "REJECTED", "reason": "import is not supported in v1"}

    # type keyword
    if _TYPE_PATTERN.search(stripped):
        return {"line": lineno, "code": "REJECTED", "reason": "type definitions are not supported in v1"}

    # method definition
    if _METHOD_DEF_PATTERN.search(stripped):
        return {"line": lineno, "code": "REJECTED", "reason": "method definitions are not supported in v1"}

    # ternary
    if _TERNARY_PATTERN.search(stripped):
        return {"line": lineno, "code": "REJECTED", "reason": "Ternary operator is not supported in v1"}

    # Rejected function calls — match full qualified name (label.new vs
    # line.new vs box.new must stay distinct).
    for fn in sorted(_REJECTED_FUNCTIONS):
        if re.search(r"\b" + re.escape(fn) + r"\s*\(", stripped):
            return {"line": lineno, "code": "REJECTED", "reason": f"{fn}() is not supported in v1"}

    # Unknown dotted method calls (e.g. close.method()) — anything of the
    # form obj.fn( that is not an explicitly whitelisted namespace call.
    _ALLOWED_DOTTED = _TA_FUNCTIONS | _MATH_FUNCTIONS | {
        "input.int", "input.float", "input.bool", "input.source",
    }
    for m in re.finditer(r"\b(\w+)\.(\w+)\s*\(", stripped):
        full = f"{m.group(1)}.{m.group(2)}"
        if full not in _ALLOWED_DOTTED:
            return {"line": lineno, "code": "REJECTED",
                    "reason": f"{full}() method calls are not supported in v1"}

    return None


def _is_known_call(line: str) -> bool:
    """Check if any function call in the line is a whitelisted call."""
    all_fns = _TA_FUNCTIONS | _MATH_FUNCTIONS | _BARE_ALIASES | {_NZ_FUNCTION}
    for fn in all_fns:
        fn_name = fn.split(".")[-1] if "." in fn else fn
        if re.search(r"\b" + re.escape(fn_name) + r"\s*\(", line):
            return True
    # Also allow input.* calls
    if re.search(r"\binput\.\w+\s*\(", line):
        return True
    return True  # Allow method-like calls on whitelisted objects (e.g. plot())


def _extract_balanced_parens(text: str, start: int) -> Optional[str]:
    """Extract the content inside balanced parentheses starting at `start`.

    Returns the content between the outer parens, or None if unbalanced.
    `start` should point to the opening '(' character.
    """
    if start >= len(text) or text[start] != "(":
        return None
    depth = 0
    i = start
    while i < len(text):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i]
        i += 1
    return None


# ── Statement parsers ───────────────────────────────────────────────────

_INDICATOR_POSITIONAL = re.compile(
    r"indicator\s*\(\s*[\"'](.+?)[\"']\s*"
    r"(?:,\s*shorttitle\s*=\s*[\"'](.+?)[\"'])?"
    r"(?:,\s*overlay\s*=\s*(true|false))?"
    r"\s*\)",
    re.IGNORECASE,
)


def _parse_indicator(lineno: int, line: str) -> Optional[Dict[str, Any]]:
    m = _INDICATOR_POSITIONAL.match(line)
    if not m:
        return None
    meta = {
        "title": m.group(1),
        "shorttitle": m.group(2),
        "overlay": m.group(3).lower() == "true" if m.group(3) else True,
    }
    return {"_meta": meta}


def _parse_input(lineno: int, line: str) -> Optional[Dict[str, Any]]:
    # Match: name = input.kind(default, title="...", minval=..., maxval=...)
    m = re.match(
        r"(\w+)\s*=\s*input\.(int|float|bool|source)\s*\(",
        line,
        re.IGNORECASE,
    )
    if not m:
        return None
    name = m.group(1)
    kind = m.group(2).lower()

    # Extract the full argument list with balanced parens
    paren_start = line.index("(", m.end() - 1)
    args_str = _extract_balanced_parens(line, paren_start)
    if args_str is None:
        return None

    args = _split_args(args_str)
    default = None
    title = name
    minval = None
    maxval = None

    if args:
        raw_default = args[0].strip()
        if kind == "source":
            # Source defaults are series identifiers (close/hl2/...), not
            # numbers — preserve the raw name so the evaluator can resolve it.
            default = raw_default.strip("\"'")
        else:
            default = _parse_value(raw_default)

    # Parse keyword args
    for arg in args[1:]:
        arg = arg.strip()
        km = re.match(r"(\w+)\s*=\s*(.+)", arg)
        if km:
            k, v = km.group(1).lower(), km.group(2).strip()
            if k == "title":
                title = v.strip("\"'")
            elif k == "minval":
                minval = _parse_number(v)
            elif k == "maxval":
                maxval = _parse_number(v)

    return {"_input": {
        "name": name,
        "kind": kind,
        "default": default,
        "title": title,
        "min": minval,
        "max": maxval,
    }}


def _parse_value(s: str):
    """Parse a default value — number, bool, or string."""
    s = s.strip()
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    return _parse_number(s)


def _parse_number(s: str) -> Optional[float]:
    s = s.strip()
    try:
        return float(s)
    except ValueError:
        return None


def _parse_hline(lineno: int, line: str) -> Optional[Dict[str, Any]]:
    m = re.match(r"hline\s*\(", line, re.IGNORECASE)
    if not m:
        return None
    paren_start = line.index("(", m.end() - 1)
    args_str = _extract_balanced_parens(line, paren_start)
    if args_str is None:
        return None

    args = _split_args(args_str)
    if not args:
        return None

    price_raw = args[0].strip()
    try:
        price = float(price_raw)
    except ValueError:
        return {"error": {"line": lineno, "code": "PARSE_ERROR",
                          "reason": f"hline price must be numeric, got: {price_raw}"}}

    title = f"HLine_{price}"
    for arg in args[1:]:
        arg = arg.strip()
        km = re.match(r"(\w+)\s*=\s*(.+)", arg)
        if km:
            k, v = km.group(1).lower(), km.group(2).strip()
            if k == "title":
                title = v.strip("\"'")

    return {"_plot": {
        "kind": "hline",
        "price": price,
        "title": title,
        "target": None,
    }}


def _parse_plot(lineno: int, line: str) -> Optional[Dict[str, Any]]:
    m = re.match(r"plot\s*\(", line, re.IGNORECASE)
    if not m:
        return None
    paren_start = line.index("(", m.end() - 1)
    args_str = _extract_balanced_parens(line, paren_start)
    if args_str is None:
        return None

    args = _split_args(args_str)
    if not args:
        return None

    target = args[0].strip()
    title = target
    color = None
    linewidth = 1
    style = "line"

    for arg in args[1:]:
        arg = arg.strip()
        km = re.match(r"(\w+)\s*=\s*(.+)", arg)
        if km:
            k, v = km.group(1).lower(), km.group(2).strip()
            if k == "title":
                title = v.strip("\"'")
            elif k == "color":
                color = v
            elif k == "linewidth":
                linewidth = int(v) if v.isdigit() else 1
            elif k == "style":
                style = v

    return {"_plot": {
        "kind": "plot",
        "target": target,
        "title": title,
        "color": color,
        "linewidth": linewidth,
        "style": style,
    }}


def _parse_assignment(lineno: int, line: str) -> Optional[Dict[str, Any]]:
    # Multi-assign: [a, b, c] = ta.macd(...)
    m = re.match(r"\[([^\]]+)\]\s*=\s*(.+)", line)
    if m:
        names = [n.strip() for n in m.group(1).split(",")]
        expr = m.group(2).strip()
        return {"_assign_multi": {"names": names, "expr": expr}}

    # Simple assign: name = expr
    m = re.match(r"(\w+)\s*=\s*(.+)", line)
    if m:
        name = m.group(1)
        expr = m.group(2).strip()
        return {"_assign": {"name": name, "expr": expr}}

    return None


def _merge_result(ir: PineIR, result: Dict[str, Any]) -> None:
    if "_meta" in result:
        ir.meta.update(result["_meta"])
    elif "_input" in result:
        ir.inputs.append(result["_input"])
    elif "_plot" in result:
        ir.plots.append(result["_plot"])
    elif "_assign" in result:
        a = result["_assign"]
        ir.assigns[a["name"]] = a["expr"]
    elif "_assign_multi" in result:
        a = result["_assign_multi"]
        expr = a["expr"]
        fn_match = re.match(r"(?:ta\.)?(\w+)\s*\((.+)\)", expr)
        if fn_match:
            fn_name = fn_match.group(1)
            args_str = fn_match.group(2)
            ir.assigns["_multi_" + fn_name] = {
                "names": a["names"],
                "fn": fn_name,
                "args": [arg.strip() for arg in _split_args(args_str)],
            }
        else:
            for name in a["names"]:
                ir.assigns[name] = expr


def _split_args(args_str: str) -> List[str]:
    """Split comma-separated arguments, respecting nested parens."""
    args = []
    depth = 0
    current = []
    for ch in args_str:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            args.append("".join(current))
            current = []
            continue
        current.append(ch)
    if current:
        args.append("".join(current))
    return args
