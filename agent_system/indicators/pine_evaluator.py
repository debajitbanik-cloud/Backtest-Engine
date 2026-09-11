"""Pine Script evaluator — pure functions over OHLCV DataFrames.

Takes a PineIR and a candle DataFrame, computes series for each plot,
and returns columns + metadata. NEVER eval/exec user code.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .pine_parser import PineIR


class EvalError(Exception):
    """Raised when the evaluator encounters a runtime error."""


def evaluate(
    ir: PineIR,
    candles: pd.DataFrame,
    inputs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate an IR against OHLCV candles."""
    if candles.empty:
        raise EvalError("No candle data provided")

    n = len(candles)
    resolved_inputs = _resolve_inputs(ir, inputs)
    context = _build_context(candles, resolved_inputs)

    columns: Dict[str, List[Optional[float]]] = {}
    errors: List[Dict[str, Any]] = []

    # Pre-compute multi-assign functions (e.g. ta.macd) so all 3 components
    # are available in context before evaluating plot expressions.
    _precompute_multi_assigns(ir, context, n)

    for plot in ir.plots:
        title = plot["title"]
        try:
            if plot["kind"] == "hline":
                columns[title] = [plot["price"]] * n
            elif plot["kind"] == "plot":
                series = _eval_expression(plot["target"], ir, context, n)
                columns[title] = series
        except EvalError as e:
            errors.append({"title": title, "error": str(e)})
            columns[title] = [None] * n

    if errors:
        msg = "; ".join(f"{e['title']}: {e['error']}" for e in errors)
        raise EvalError(msg)

    return {
        "columns": columns,
        "meta": ir.meta,
        "inputs": resolved_inputs,
    }


# ── Input resolution ────────────────────────────────────────────────────

def _resolve_inputs(
    ir: PineIR,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    resolved = {}
    for inp in ir.inputs:
        name = inp["name"]
        if overrides and name in overrides:
            resolved[name] = overrides[name]
        else:
            resolved[name] = inp["default"]
    return resolved


# ── Context (series + builtins) ─────────────────────────────────────────

def _build_context(
    candles: pd.DataFrame,
    resolved_inputs: Dict[str, Any],
) -> Dict[str, Any]:
    """Build evaluation context with series builtins and input values."""
    ctx: Dict[str, Any] = {}

    # Series builtins
    ctx["open"] = candles["open"].tolist()
    ctx["high"] = candles["high"].tolist()
    ctx["low"] = candles["low"].tolist()
    ctx["close"] = candles["close"].tolist()
    ctx["volume"] = candles["volume"].tolist()

    # Derived series
    h = candles["high"].tolist()
    l = candles["low"].tolist()
    o = candles["open"].tolist()
    c = candles["close"].tolist()
    ctx["hl2"] = [(hi + lo) / 2 for hi, lo in zip(h, l)]
    ctx["hlc3"] = [(hi + lo + cl) / 3 for hi, lo, cl in zip(h, l, c)]
    ctx["ohlc4"] = [(op + hi + lo + cl) / 4 for op, hi, lo, cl in zip(o, h, l, c)]

    # Inputs — string values naming a known series (input.source) resolve
    # to that series so plot(src) yields numbers, not the name itself.
    for name, value in resolved_inputs.items():
        if isinstance(value, str) and value in ctx:
            series = ctx[value]
            ctx[name] = list(series) if isinstance(series, list) else series
        else:
            ctx[name] = value

    return ctx


# ── Multi-assign precomputation ─────────────────────────────────────────

def _precompute_multi_assigns(
    ir: PineIR,
    ctx: Dict[str, Any],
    n: int,
) -> None:
    """Pre-compute multi-assign functions (ta.macd) and store all outputs."""
    for key, val in list(ir.assigns.items()):
        if key.startswith("_multi_") and isinstance(val, dict):
            fn_name = val["fn"]
            names = val["names"]
            args = val["args"]
            if fn_name == "macd":
                # Resolve args
                resolved_args = []
                for arg in args:
                    arg = arg.strip()
                    try:
                        resolved_args.append(float(arg))
                    except ValueError:
                        resolved_args.append(arg)
                _compute_macd(resolved_args, ctx, n, names)


def _compute_macd(
    args: List, ctx: Dict[str, Any], n: int, names: List[str]
) -> None:
    """Compute MACD line, signal, and histogram, store in context."""
    if len(args) != 4:
        raise EvalError("ta.macd requires 4 arguments")
    source = _resolve_series(args[0], ctx, n)
    fast = int(args[1]) if isinstance(args[1], (int, float)) else int(_resolve_series(args[1], ctx, n)[0])
    slow = int(args[2]) if isinstance(args[2], (int, float)) else int(_resolve_series(args[2], ctx, n)[0])
    signal = int(args[3]) if isinstance(args[3], (int, float)) else int(_resolve_series(args[3], ctx, n)[0])

    k_fast = 2.0 / (fast + 1)
    k_slow = 2.0 / (slow + 1)
    ema_fast = source[0]
    ema_slow = source[0]
    macd_line = []
    for i in range(n):
        ema_fast = source[i] * k_fast + ema_fast * (1 - k_fast)
        ema_slow = source[i] * k_slow + ema_slow * (1 - k_slow)
        macd_line.append(ema_fast - ema_slow)

    k_signal = 2.0 / (signal + 1)
    sig_line = [macd_line[0]]
    sig_ema = macd_line[0]
    for i in range(1, n):
        sig_ema = macd_line[i] * k_signal + sig_ema * (1 - k_signal)
        sig_line.append(sig_ema)

    hist = [m - s for m, s in zip(macd_line, sig_line)]

    # Store by the variable names from multi-assign
    if len(names) >= 1:
        ctx[names[0]] = macd_line
    if len(names) >= 2:
        ctx[names[1]] = sig_line
    if len(names) >= 3:
        ctx[names[2]] = hist


# ── Expression evaluator ────────────────────────────────────────────────

def _eval_expression(
    expr: str,
    ir: PineIR,
    ctx: Dict[str, Any],
    n: int,
) -> List[Optional[float]]:
    """Evaluate a single expression and return a series of length n."""
    expr = expr.strip()

    # Literal number
    try:
        val = float(expr)
        return [val] * n
    except ValueError:
        pass

    # Direct context reference (series, input, or computed)
    if expr in ctx:
        val = ctx[expr]
        if isinstance(val, list):
            return val
        return [val] * n

    # Ternary (rejected at parse time, but just in case)
    if "?" in expr:
        raise EvalError("Ternary operator not supported")

    # Binary operations: split on +, -, *, /
    binop = _split_binary_op(expr)
    if binop is not None:
        left, op, right = binop
        left_series = _eval_expression(left, ir, ctx, n)
        right_series = _eval_expression(right, ir, ctx, n)
        return _apply_binary_op(left_series, op, right_series, n)

    # Function calls — use balanced paren extraction
    fn_match = re.match(r"((?:ta|math|nz)\.)?(\w+)\s*\(", expr)
    if fn_match:
        prefix = fn_match.group(1) or ""
        fn_name = prefix + fn_match.group(2)
        paren_start = expr.index("(", fn_match.end() - 1)
        args_str = _extract_balanced_parens(expr, paren_start)
        if args_str is not None:
            raw_args = _split_args(args_str)
            # Evaluate each arg as an expression (handles nested binary ops)
            eval_args = [_eval_arg(a.strip(), ir, ctx, n) for a in raw_args]
            return _eval_function(fn_name, eval_args, ir, ctx, n)

    # Variable reference — look up in assigns
    if expr in ir.assigns:
        inner = ir.assigns[expr]
        if isinstance(inner, str):
            return _eval_expression(inner, ir, ctx, n)

    raise EvalError(f"Cannot evaluate expression: {expr}")


def _eval_arg(
    arg: str,
    ir: PineIR,
    ctx: Dict[str, Any],
    n: int,
) -> Any:
    """Evaluate a function argument — returns float, series list, or string ref."""
    arg = arg.strip()
    # Try literal number
    try:
        return float(arg)
    except ValueError:
        pass
    # Try evaluating as expression (handles binary ops, function calls)
    try:
        return _eval_expression(arg, ir, ctx, n)
    except EvalError:
        pass
    # Return as string reference for _resolve_series
    return arg


def _apply_binary_op(
    left: List[Optional[float]],
    op: str,
    right: List[Optional[float]],
    n: int,
) -> List[Optional[float]]:
    """Apply a binary operator element-wise."""
    result = []
    for i in range(n):
        l = left[i] if i < len(left) else None
        r = right[i] if i < len(right) else None
        if l is None or r is None:
            result.append(None)
            continue
        if op == "+":
            result.append(l + r)
        elif op == "-":
            result.append(l - r)
        elif op == "*":
            result.append(l * r)
        elif op == "/":
            result.append(l / r if r != 0 else None)
        else:
            raise EvalError(f"Unknown operator: {op}")
    return result


def _split_binary_op(expr: str) -> Optional[Tuple[str, str, str]]:
    """Split expression on lowest-precedence binary operator.

    Respects parentheses. Returns (left, op, right) or None.
    """
    depth = 0
    last_op_pos = -1
    last_op = None
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and ch in "+-*/":
            # For * and /, only split if no + or - found yet (precedence)
            if ch in "*/" and last_op is not None and last_op in "+-":
                pass
            else:
                last_op_pos = i
                last_op = ch
        i += 1

    if last_op_pos > 0:
        left = expr[:last_op_pos].strip()
        right = expr[last_op_pos + 1:].strip()
        if left and right:
            return (left, last_op, right)
    return None


def _extract_balanced_parens(text: str, start: int) -> Optional[str]:
    """Extract content inside balanced parens starting at `start` (the '(')."""
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


# ── Function evaluation ─────────────────────────────────────────────────

def _eval_function(
    fn_name: str,
    args: List[Any],
    ir: PineIR,
    ctx: Dict[str, Any],
    n: int,
) -> List[Optional[float]]:
    """Dispatch to the appropriate function evaluator."""
    if fn_name in ("ta.sma", "sma"):
        return _eval_sma(args, ctx, n)
    elif fn_name in ("ta.ema", "ema"):
        return _eval_ema(args, ctx, n)
    elif fn_name in ("ta.rsi", "rsi"):
        return _eval_rsi(args, ctx, n)
    elif fn_name in ("ta.macd",):
        return _eval_macd(args, ir, ctx, n)
    elif fn_name == "math.abs":
        return _eval_math_abs(args, ctx, n)
    elif fn_name == "math.max":
        return _eval_math_max(args, ctx, n)
    elif fn_name == "math.min":
        return _eval_math_min(args, ctx, n)
    elif fn_name == "nz":
        return _eval_nz(args, ctx, n)
    else:
        raise EvalError(f"Function not supported: {fn_name}")


def _resolve_series(arg, ctx: Dict[str, Any], n: int) -> List[float]:
    """Resolve an argument to a numeric series."""
    if isinstance(arg, (int, float)):
        return [float(arg)] * n
    if isinstance(arg, list):
        # Already a computed series
        return [float(v) if v is not None else float("nan") for v in arg]
    if isinstance(arg, str):
        if arg in ctx:
            val = ctx[arg]
            if isinstance(val, list):
                return [float(v) if v is not None else float("nan") for v in val]
            return [float(val)] * n
        raise EvalError(f"Unknown series: {arg}")
    raise EvalError(f"Cannot resolve argument: {arg}")


def _eval_sma(args: List, ctx: Dict[str, Any], n: int) -> List[Optional[float]]:
    """ta.sma(source, length) — Simple Moving Average."""
    if len(args) != 2:
        raise EvalError("ta.sma requires exactly 2 arguments: source, length")
    source = _resolve_series(args[0], ctx, n)
    length = int(args[1]) if isinstance(args[1], (int, float)) else int(_resolve_series(args[1], ctx, n)[0])

    if length <= 0:
        raise EvalError("SMA length must be positive")
    if length > n:
        raise EvalError(f"SMA length ({length}) exceeds candle count ({n})")

    result: List[Optional[float]] = [None] * (length - 1)
    for i in range(length - 1, n):
        window = source[i - length + 1 : i + 1]
        result.append(sum(window) / length)
    return result


def _eval_ema(args: List, ctx: Dict[str, Any], n: int) -> List[Optional[float]]:
    """ta.ema(source, length) — Exponential Moving Average."""
    if len(args) != 2:
        raise EvalError("ta.ema requires exactly 2 arguments: source, length")
    source = _resolve_series(args[0], ctx, n)
    length = int(args[1]) if isinstance(args[1], (int, float)) else int(_resolve_series(args[1], ctx, n)[0])

    if length <= 0:
        raise EvalError("EMA length must be positive")

    k = 2.0 / (length + 1)
    result = [source[0]]
    ema = source[0]
    for i in range(1, n):
        ema = source[i] * k + ema * (1 - k)
        result.append(ema)
    return result


def _eval_rsi(args: List, ctx: Dict[str, Any], n: int) -> List[Optional[float]]:
    """ta.rsi(source, length) — Relative Strength Index."""
    if len(args) != 2:
        raise EvalError("ta.rsi requires exactly 2 arguments: source, length")
    source = _resolve_series(args[0], ctx, n)
    length = int(args[1]) if isinstance(args[1], (int, float)) else int(_resolve_series(args[1], ctx, n)[0])

    if length <= 0:
        raise EvalError("RSI length must be positive")
    if length + 1 > n:
        raise EvalError(f"RSI length ({length}) requires at least {length + 1} candles, got {n}")

    result: List[Optional[float]] = [None] * length
    for i in range(length, n):
        gains, losses = 0.0, 0.0
        for j in range(i - length + 1, i + 1):
            diff = source[j] - source[j - 1]
            if diff > 0:
                gains += diff
            else:
                losses -= diff
        if losses == 0:
            result.append(100.0)
        else:
            rs = (gains / length) / (losses / length)
            result.append(100.0 - 100.0 / (1.0 + rs))
    return result


def _eval_macd(
    args: List, ir: PineIR, ctx: Dict[str, Any], n: int
) -> List[Optional[float]]:
    """ta.macd(source, fast, slow, signal) — returns MACD line."""
    if len(args) != 4:
        raise EvalError("ta.macd requires exactly 4 arguments: source, fast, slow, signal")
    source = _resolve_series(args[0], ctx, n)
    fast = int(args[1]) if isinstance(args[1], (int, float)) else int(_resolve_series(args[1], ctx, n)[0])
    slow = int(args[2]) if isinstance(args[2], (int, float)) else int(_resolve_series(args[2], ctx, n)[0])
    signal = int(args[3]) if isinstance(args[3], (int, float)) else int(_resolve_series(args[3], ctx, n)[0])

    if fast <= 0 or slow <= 0 or signal <= 0:
        raise EvalError("MACD periods must be positive")

    k_fast = 2.0 / (fast + 1)
    k_slow = 2.0 / (slow + 1)
    ema_fast = source[0]
    ema_slow = source[0]
    macd_line = []
    for i in range(n):
        ema_fast = source[i] * k_fast + ema_fast * (1 - k_fast)
        ema_slow = source[i] * k_slow + ema_slow * (1 - k_slow)
        macd_line.append(ema_fast - ema_slow)

    k_signal = 2.0 / (signal + 1)
    sig_line = [macd_line[0]]
    sig_ema = macd_line[0]
    for i in range(1, n):
        sig_ema = macd_line[i] * k_signal + sig_ema * (1 - k_signal)
        sig_line.append(sig_ema)

    hist = [m - s for m, s in zip(macd_line, sig_line)]

    ctx["_macd_line"] = macd_line
    ctx["_macd_signal"] = sig_line
    ctx["_macd_hist"] = hist

    return macd_line


def _eval_math_abs(args: List, ctx: Dict[str, Any], n: int) -> List[Optional[float]]:
    """math.abs(x)"""
    if len(args) != 1:
        raise EvalError("math.abs requires 1 argument")
    series = _resolve_series(args[0], ctx, n)
    return [abs(v) if not np.isnan(v) else None for v in series]


def _eval_math_max(args: List, ctx: Dict[str, Any], n: int) -> List[Optional[float]]:
    """math.max(a, b)"""
    if len(args) != 2:
        raise EvalError("math.max requires 2 arguments")
    a = _resolve_series(args[0], ctx, n)
    b = _resolve_series(args[1], ctx, n)
    return [max(ai, bi) if not (np.isnan(ai) or np.isnan(bi)) else None for ai, bi in zip(a, b)]


def _eval_math_min(args: List, ctx: Dict[str, Any], n: int) -> List[Optional[float]]:
    """math.min(a, b)"""
    if len(args) != 2:
        raise EvalError("math.min requires 2 arguments")
    a = _resolve_series(args[0], ctx, n)
    b = _resolve_series(args[1], ctx, n)
    return [min(ai, bi) if not (np.isnan(ai) or np.isnan(bi)) else None for ai, bi in zip(a, b)]


def _eval_nz(args: List, ctx: Dict[str, Any], n: int) -> List[Optional[float]]:
    """nz(source, replacement) — replace NaN with replacement."""
    if len(args) < 1 or len(args) > 2:
        raise EvalError("nz requires 1 or 2 arguments")
    source = _resolve_series(args[0], ctx, n)
    replacement = float(args[1]) if len(args) > 1 else 0.0
    return [v if not np.isnan(v) else replacement for v in source]
