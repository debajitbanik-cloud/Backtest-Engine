"""Tests for Pine Script parser and evaluator.

Fixtures cover:
  - Valid v4 and v5 scripts (SMA, EMA, RSI, MACD, multi-plot, hline, inputs)
  - Every rejected construct → parser returns per-line errors
  - Evaluator vs hand-computed SMA/EMA/RSI on fixture candles
"""
import sys
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent_system.indicators.pine_parser import parse_pine, PineParseError
from agent_system.indicators.pine_evaluator import evaluate, EvalError


# ---------------------------------------------------------------------------
# Fixture candles — 30 bars of rising-close OHLCV for deterministic math
# ---------------------------------------------------------------------------
def _make_candles(n: int = 30, start: float = 100.0) -> pd.DataFrame:
    rows = []
    for i in range(n):
        o = start + i
        h = o + 1
        l = o - 1
        c = o + 0.5
        rows.append({"open": o, "high": h, "low": l, "close": c, "volume": 1000 + i})
    return pd.DataFrame(rows)


CANDLES = _make_candles(30)


# ---------------------------------------------------------------------------
# Hand-computed reference values for 30-bar rising close series
# ---------------------------------------------------------------------------
def _hand_sma(closes: list, period: int) -> list:
    out = [None] * (period - 1)
    for i in range(period - 1, len(closes)):
        out.append(sum(closes[i - period + 1 : i + 1]) / period)
    return out


def _hand_ema(closes: list, period: int) -> list:
    k = 2.0 / (period + 1)
    ema = closes[0]
    out = [closes[0]]
    for c in closes[1:]:
        ema = c * k + ema * (1 - k)
        out.append(ema)
    # pad to length (EMA fills from index 0)
    return out


def _hand_rsi(closes: list, period: int) -> list:
    out = [None] * period
    for i in range(period, len(closes)):
        gains, losses = 0.0, 0.0
        for j in range(i - period + 1, i + 1):
            diff = closes[j] - closes[j - 1]
            if diff > 0:
                gains += diff
            else:
                losses -= diff
        if losses == 0:
            out.append(100.0)
        else:
            rs = (gains / period) / (losses / period)
            out.append(100.0 - 100.0 / (1.0 + rs))
    return out


CLOSES = CANDLES["close"].tolist()
HL2 = [(h + l) / 2 for h, l in zip(CANDLES["high"], CANDLES["low"])]
HLC3 = [(h + l + c) / 3 for h, l, c in zip(CANDLES["high"], CANDLES["low"], CANDLES["close"])]
OHLC4 = [(o + h + l + c) / 4 for o, h, l, c in zip(CANDLES["open"], CANDLES["high"], CANDLES["low"], CANDLES["close"])]


# ═══════════════════════════════════════════════════════════════════════════
# Parser — valid scripts
# ═══════════════════════════════════════════════════════════════════════════

class TestParserValidScripts:

    def test_v5_simple_sma(self):
        code = """
//@version=5
indicator("SMA 20", overlay=true)
sma_val = ta.sma(close, 20)
plot(sma_val, title="SMA", color=color.blue)
"""
        ir = parse_pine(code)
        assert ir.meta["version"] == 5
        assert ir.meta["title"] == "SMA 20"
        assert ir.meta["overlay"] is True
        assert len(ir.plots) == 1
        assert ir.plots[0]["target"] == "sma_val"
        assert ir.plots[0]["title"] == "SMA"

    def test_v4_simple_sma(self):
        code = """
//@version=4
indicator("My SMA")
sma_val = sma(close, 14)
plot(sma_val)
"""
        ir = parse_pine(code)
        assert ir.meta["version"] == 4
        assert len(ir.plots) == 1

    def test_v4_with_input_int(self):
        code = """
//@version=4
indicator("Input Test")
len = input.int(14, title="Period", minval=2, maxval=200)
sma_val = sma(close, len)
plot(sma_val)
"""
        ir = parse_pine(code)
        assert len(ir.inputs) == 1
        inp = ir.inputs[0]
        assert inp["name"] == "len"
        assert inp["kind"] == "int"
        assert inp["default"] == 14
        assert inp["min"] == 2
        assert inp["max"] == 200

    def test_v5_input_float(self):
        code = """
//@version=5
indicator("Float Input")
mult = input.float(2.0, title="Multiplier", minval=0.1, maxval=10.0)
plot(close * mult)
"""
        ir = parse_pine(code)
        assert len(ir.inputs) == 1
        inp = ir.inputs[0]
        assert inp["kind"] == "float"
        assert inp["default"] == 2.0

    def test_v5_input_bool(self):
        code = """
//@version=5
indicator("Bool Input")
show = input.bool(true, title="Show Band")
plot(show ? close : na)
"""
        ir = parse_pine(code)
        assert ir.inputs[0]["kind"] == "bool"
        assert ir.inputs[0]["default"] is True

    def test_v5_input_source(self):
        code = """
//@version=5
indicator("Source Input")
src = input.source(close, title="Source")
plot(src)
"""
        ir = parse_pine(code)
        assert ir.inputs[0]["kind"] == "source"

    def test_multi_plot(self):
        code = """
//@version=5
indicator("Multi Plot", overlay=true)
sma20 = ta.sma(close, 20)
sma50 = ta.sma(close, 50)
plot(sma20, color=color.blue)
plot(sma50, color=color.red)
"""
        ir = parse_pine(code)
        assert len(ir.plots) == 2

    def test_hline(self):
        code = """
//@version=5
indicator("HLine Test")
hline(100.0, title="Zero Line", color=color.gray)
"""
        ir = parse_pine(code)
        assert len(ir.plots) == 1
        assert ir.plots[0]["kind"] == "hline"
        assert ir.plots[0]["price"] == 100.0

    def test_ta_ema(self):
        code = """
//@version=5
indicator("EMA Test")
ema_val = ta.ema(close, 12)
plot(ema_val)
"""
        ir = parse_pine(code)
        assert len(ir.plots) == 1

    def test_ta_rsi(self):
        code = """
//@version=5
indicator("RSI Test")
rsi_val = ta.rsi(close, 14)
plot(rsi_val)
"""
        ir = parse_pine(code)
        assert len(ir.plots) == 1

    def test_ta_macd(self):
        code = """
//@version=5
indicator("MACD Test")
[macd_line, signal_line, hist] = ta.macd(close, 12, 26, 9)
plot(macd_line, title="MACD")
plot(signal_line, title="Signal")
plot(hist, title="Hist")
"""
        ir = parse_pine(code)
        assert len(ir.plots) == 3

    def test_v4_bare_sma_alias(self):
        """v4 bare sma() alias should parse correctly."""
        code = """
//@version=4
indicator("Bare SMA")
plot(sma(close, 20))
"""
        ir = parse_pine(code)
        assert len(ir.plots) == 1

    def test_v4_bare_ema_alias(self):
        code = """
//@version=4
indicator("Bare EMA")
plot(ema(close, 10))
"""
        ir = parse_pine(code)
        assert len(ir.plots) == 1

    def test_v4_bare_rsi_alias(self):
        code = """
//@version=4
indicator("Bare RSI")
plot(rsi(close, 14))
"""
        ir = parse_pine(code)
        assert len(ir.plots) == 1

    def test_binary_ops(self):
        code = """
//@version=5
indicator("Binary Ops")
result = close * 2 + open - low / high
plot(result)
"""
        ir = parse_pine(code)
        assert len(ir.plots) == 1

    def test_math_functions(self):
        code = """
//@version=5
indicator("Math Fns")
val = math.max(math.min(close, 200), 0)
plot(val)
"""
        ir = parse_pine(code)
        assert len(ir.plots) == 1

    def test_nz_function(self):
        code = """
//@version=5
indicator("NZ Test")
src = nz(close, 0)
plot(src)
"""
        ir = parse_pine(code)
        assert len(ir.plots) == 1

    def test_overlay_false(self):
        code = """
//@version=5
indicator("Separate Pane", overlay=false)
plot(close)
"""
        ir = parse_pine(code)
        assert ir.meta["overlay"] is False

    def test_shorttitle(self):
        code = """
//@version=5
indicator("Full Title", shorttitle="Short")
plot(close)
"""
        ir = parse_pine(code)
        assert ir.meta["shorttitle"] == "Short"

    def test_empty_script_no_indicator(self):
        """Script with only version comment — no indicator() call."""
        code = """//@version=5"""
        ir = parse_pine(code)
        # Should parse without error but have no meta/plots
        assert len(ir.plots) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Parser — rejected constructs
# ═══════════════════════════════════════════════════════════════════════════

class TestParserRejectedConstructs:

    def _parse_errors(self, code: str) -> List[Dict[str, Any]]:
        result = parse_pine(code)
        return result.errors

    def test_strategy_call_rejected(self):
        code = """
//@version=5
strategy("My Strategy")
plot(close)
"""
        errors = self._parse_errors(code)
        assert any("strategy" in e.get("reason", "").lower() for e in errors)

    def test_request_function_rejected(self):
        code = """
//@version=5
indicator("Request Test")
data = request.security("AAPL", "1D", close)
plot(data)
"""
        errors = self._parse_errors(code)
        assert any("request" in e.get("reason", "").lower() for e in errors)

    def test_loop_rejected(self):
        code = """
//@version=5
indicator("Loop Test")
for i = 0 to 10
    plot(close + i)
"""
        errors = self._parse_errors(code)
        assert any("loop" in e.get("reason", "").lower() or "for" in e.get("reason", "").lower() for e in errors)

    def test_varip_rejected(self):
        code = """
//@version=5
indicator("Varip Test")
varip x = 0
plot(x)
"""
        errors = self._parse_errors(code)
        assert any("varip" in e.get("reason", "").lower() for e in errors)

    def test_fill_rejected(self):
        code = """
//@version=5
indicator("Fill Test")
a = plot(close)
b = plot(close * 1.01)
fill(a, b)
"""
        errors = self._parse_errors(code)
        assert any("fill" in e.get("reason", "").lower() for e in errors)

    def test_bgcolor_rejected(self):
        code = """
//@version=5
indicator("BGColor Test")
bgcolor(color.red)
"""
        errors = self._parse_errors(code)
        assert any("bgcolor" in e.get("reason", "").lower() for e in errors)

    def test_barcolor_rejected(self):
        code = """
//@version=5
indicator("BarColor Test")
barcolor(color.blue)
"""
        errors = self._parse_errors(code)
        assert any("barcolor" in e.get("reason", "").lower() for e in errors)

    def test_label_new_rejected(self):
        code = """
//@version=5
indicator("Label Test")
label.new(bar_index, close, "Hi")
"""
        errors = self._parse_errors(code)
        assert any("label" in e.get("reason", "").lower() for e in errors)

    def test_box_new_rejected(self):
        code = """
//@version=5
indicator("Box Test")
box.new(bar_index, close, bar_index + 10, close * 1.01)
"""
        errors = self._parse_errors(code)
        assert any("box" in e.get("reason", "").lower() for e in errors)

    def test_line_new_rejected(self):
        code = """
//@version=5
indicator("Line Test")
line.new(bar_index, close, bar_index + 10, close)
"""
        errors = self._parse_errors(code)
        assert any("line" in e.get("reason", "").lower() for e in errors)

    def test_ternary_rejected(self):
        """Ternary operator not in v1 subset."""
        code = """
//@version=5
indicator("Ternary")
x = close > open ? close : open
plot(x)
"""
        errors = self._parse_errors(code)
        assert any("ternary" in e.get("reason", "").lower() or "?" in e.get("reason", "").lower() for e in errors)

    def test_unknown_function_rejected(self):
        code = """
//@version=5
indicator("Unknown Fn")
plot(ta.stoch(close, high, low, 14))
"""
        errors = self._parse_errors(code)
        assert any("stoch" in e.get("reason", "").lower() or "not supported" in e.get("reason", "").lower() for e in errors)

    def test_import_rejected(self):
        code = """
//@version=5
indicator("Import Test")
import MyLib
plot(close)
"""
        errors = self._parse_errors(code)
        assert any("import" in e.get("reason", "").lower() for e in errors)

    def test_type_keyword_rejected(self):
        code = """
//@version=5
indicator("Type Test")
type MyType
    float field = 0.0
plot(close)
"""
        errors = self._parse_errors(code)
        assert any("type" in e.get("reason", "").lower() for e in errors)

    def test_method_rejected(self):
        code = """
//@version=5
indicator("Method Test")
method float.method(self) =>
    self
plot(close)
"""
        errors = self._parse_errors(code)
        assert any("method" in e.get("reason", "").lower() or "not supported" in e.get("reason", "").lower() for e in errors)

    def test_method_call_rejected(self):
        code = """
//@version=5
indicator("Method Call")
x = close.method()
plot(x)
"""
        errors = self._parse_errors(code)
        assert len(errors) > 0


# ═══════════════════════════════════════════════════════════════════════════
# Evaluator — hand-computed correctness
# ═══════════════════════════════════════════════════════════════════════════

class TestEvaluatorSMA:

    def test_sma_20_matches_hand(self):
        code = """
//@version=5
indicator("SMA Test")
sma_val = ta.sma(close, 20)
plot(sma_val, title="SMA")
"""
        ir = parse_pine(code)
        result = evaluate(ir, CANDLES)
        series = result["columns"]["SMA"]
        hand = _hand_sma(CLOSES, 20)
        for i, (got, exp) in enumerate(zip(series, hand)):
            if exp is None:
                assert got is None or (isinstance(got, float) and pd.isna(got)), f"bar {i}: expected None, got {got}"
            else:
                assert got == pytest.approx(exp, rel=1e-10), f"bar {i}: got {got}, expected {exp}"

    def test_sma_14_matches_hand(self):
        code = """
//@version=4
indicator("SMA14")
plot(sma(close, 14))
"""
        ir = parse_pine(code)
        result = evaluate(ir, CANDLES)
        series = list(result["columns"].values())[0]
        hand = _hand_sma(CLOSES, 14)
        for i, (got, exp) in enumerate(zip(series, hand)):
            if exp is None:
                assert got is None or (isinstance(got, float) and pd.isna(got))
            else:
                assert got == pytest.approx(exp, rel=1e-10)


class TestEvaluatorEMA:

    def test_ema_12_matches_hand(self):
        code = """
//@version=5
indicator("EMA Test")
ema_val = ta.ema(close, 12)
plot(ema_val, title="EMA")
"""
        ir = parse_pine(code)
        result = evaluate(ir, CANDLES)
        series = result["columns"]["EMA"]
        hand = _hand_ema(CLOSES, 12)
        for i, (got, exp) in enumerate(zip(series, hand)):
            assert got == pytest.approx(exp, rel=1e-10), f"bar {i}: got {got}, expected {exp}"


class TestEvaluatorRSI:

    def test_rsi_14_matches_hand(self):
        code = """
//@version=5
indicator("RSI Test")
rsi_val = ta.rsi(close, 14)
plot(rsi_val, title="RSI")
"""
        ir = parse_pine(code)
        result = evaluate(ir, CANDLES)
        series = result["columns"]["RSI"]
        hand = _hand_rsi(CLOSES, 14)
        for i, (got, exp) in enumerate(zip(series, hand)):
            if exp is None:
                assert got is None or (isinstance(got, float) and pd.isna(got))
            else:
                assert got == pytest.approx(exp, rel=1e-6), f"bar {i}: got {got}, expected {exp}"


class TestEvaluatorMACD:

    def test_macd_line(self):
        code = """
//@version=5
indicator("MACD")
[macd_line, signal_line, hist] = ta.macd(close, 12, 26, 9)
plot(macd_line, title="MACD")
plot(signal_line, title="Signal")
plot(hist, title="Hist")
"""
        ir = parse_pine(code)
        result = evaluate(ir, CANDLES)
        assert "MACD" in result["columns"]
        assert "Signal" in result["columns"]
        assert "Hist" in result["columns"]
        # MACD line = EMA(12) - EMA(26)
        ema12 = _hand_ema(CLOSES, 12)
        ema26 = _hand_ema(CLOSES, 26)
        macd_hand = [a - b for a, b in zip(ema12, ema26)]
        for i, (got, exp) in enumerate(zip(result["columns"]["MACD"], macd_hand)):
            assert got == pytest.approx(exp, rel=1e-10), f"bar {i}"


class TestEvaluatorSeriesBuiltins:

    def test_hl2(self):
        code = """
//@version=5
indicator("HL2 Test")
plot(hl2, title="HL2")
"""
        ir = parse_pine(code)
        result = evaluate(ir, CANDLES)
        series = result["columns"]["HL2"]
        for i, (got, exp) in enumerate(zip(series, HL2)):
            assert got == pytest.approx(exp, rel=1e-10)

    def test_hlc3(self):
        code = """
//@version=5
indicator("HLC3 Test")
plot(hlc3, title="HLC3")
"""
        ir = parse_pine(code)
        result = evaluate(ir, CANDLES)
        series = result["columns"]["HLC3"]
        for i, (got, exp) in enumerate(zip(series, HLC3)):
            assert got == pytest.approx(exp, rel=1e-10)

    def test_ohlc4(self):
        code = """
//@version=5
indicator("OHLC4 Test")
plot(ohlc4, title="OHLC4")
"""
        ir = parse_pine(code)
        result = evaluate(ir, CANDLES)
        series = result["columns"]["OHLC4"]
        for i, (got, exp) in enumerate(zip(series, OHLC4)):
            assert got == pytest.approx(exp, rel=1e-10)

    def test_close_passthrough(self):
        code = """
//@version=5
indicator("Close Test")
plot(close, title="Close")
"""
        ir = parse_pine(code)
        result = evaluate(ir, CANDLES)
        series = result["columns"]["Close"]
        for i, (got, exp) in enumerate(zip(series, CLOSES)):
            assert got == pytest.approx(exp, rel=1e-10)


class TestEvaluatorHLine:

    def test_hline(self):
        code = """
//@version=5
indicator("HLine Test")
hline(100.0, title="Zero", color=color.gray)
"""
        ir = parse_pine(code)
        result = evaluate(ir, CANDLES)
        series = result["columns"]["Zero"]
        for v in series:
            assert v == 100.0


class TestEvaluatorInputOverrides:

    def test_input_int_overridden(self):
        code = """
//@version=5
indicator("Input Override")
len = input.int(20, title="Period")
sma_val = ta.sma(close, len)
plot(sma_val, title="SMA")
"""
        ir = parse_pine(code)
        result = evaluate(ir, CANDLES, inputs={"len": 10})
        series = result["columns"]["SMA"]
        hand = _hand_sma(CLOSES, 10)
        for i, (got, exp) in enumerate(zip(series, hand)):
            if exp is None:
                assert got is None or (isinstance(got, float) and pd.isna(got))
            else:
                assert got == pytest.approx(exp, rel=1e-10)


class TestEvaluatorBinaryOps:

    def test_binary_ops(self):
        code = """
//@version=5
indicator("Binary Ops")
result = close * 2 + open - low
plot(result, title="Result")
"""
        ir = parse_pine(code)
        result = evaluate(ir, CANDLES)
        series = result["columns"]["Result"]
        for i in range(len(CANDLES)):
            exp = CLOSES[i] * 2 + CANDLES["open"].iloc[i] - CANDLES["low"].iloc[i]
            assert series[i] == pytest.approx(exp, rel=1e-10)


class TestEvaluatorMathFunctions:

    def test_math_max(self):
        code = """
//@version=5
indicator("Math Max")
plot(math.max(close, 150), title="Max")
"""
        ir = parse_pine(code)
        result = evaluate(ir, CANDLES)
        series = result["columns"]["Max"]
        for i in range(len(CANDLES)):
            assert series[i] == pytest.approx(max(CLOSES[i], 150), rel=1e-10)

    def test_math_min(self):
        code = """
//@version=5
indicator("Math Min")
plot(math.min(close, 110), title="Min")
"""
        ir = parse_pine(code)
        result = evaluate(ir, CANDLES)
        series = result["columns"]["Min"]
        for i in range(len(CANDLES)):
            assert series[i] == pytest.approx(min(CLOSES[i], 110), rel=1e-10)

    def test_math_abs(self):
        code = """
//@version=5
indicator("Math Abs")
plot(math.abs(close - 115), title="Abs")
"""
        ir = parse_pine(code)
        result = evaluate(ir, CANDLES)
        series = result["columns"]["Abs"]
        for i in range(len(CANDLES)):
            assert series[i] == pytest.approx(abs(CLOSES[i] - 115), rel=1e-10)


class TestEvaluatorNz:

    def test_nz(self):
        code = """
//@version=5
indicator("NZ Test")
plot(nz(close, 0), title="NZ")
"""
        ir = parse_pine(code)
        result = evaluate(ir, CANDLES)
        series = result["columns"]["NZ"]
        for i in range(len(CANDLES)):
            assert series[i] == pytest.approx(CLOSES[i], rel=1e-10)


class TestEvaluatorInputSource:

    def test_input_source_hl2(self):
        code = """
//@version=5
indicator("Source Test")
src = input.source(hl2, title="Source")
plot(src, title="Src")
"""
        ir = parse_pine(code)
        result = evaluate(ir, CANDLES, inputs={"src": "hl2"})
        series = result["columns"]["Src"]
        for i, (got, exp) in enumerate(zip(series, HL2)):
            assert got == pytest.approx(exp, rel=1e-10)


class TestEvaluatorErrors:

    def test_sma_period_too_large(self):
        code = """
//@version=5
indicator("SMA Big")
sma_val = ta.sma(close, 100)
plot(sma_val, title="SMA")
"""
        ir = parse_pine(code)
        with pytest.raises(EvalError):
            evaluate(ir, CANDLES)

    def test_rsi_period_too_large(self):
        code = """
//@version=5
indicator("RSI Big")
rsi_val = ta.rsi(close, 100)
plot(rsi_val, title="RSI")
"""
        ir = parse_pine(code)
        with pytest.raises(EvalError):
            evaluate(ir, CANDLES)


class TestEvaluatorMultiPlot:

    def test_multi_plot_columns(self):
        code = """
//@version=5
indicator("Multi")
sma10 = ta.sma(close, 10)
sma20 = ta.sma(close, 20)
plot(sma10, title="Fast")
plot(sma20, title="Slow")
"""
        ir = parse_pine(code)
        result = evaluate(ir, CANDLES)
        assert "Fast" in result["columns"]
        assert "Slow" in result["columns"]
        assert len(result["columns"]) == 2


# ═══════════════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════════════

class TestEdgeCases:

    def test_empty_candles_evaluator(self):
        code = """
//@version=5
indicator("Empty")
plot(close)
"""
        ir = parse_pine(code)
        with pytest.raises(EvalError):
            evaluate(ir, pd.DataFrame(columns=["open", "high", "low", "close", "volume"]))

    def test_single_candle(self):
        code = """
//@version=5
indicator("Single")
plot(close)
"""
        ir = parse_pine(code)
        result = evaluate(ir, CANDLES.iloc[:1])
        assert len(result["columns"]["close"]) == 1

    def test_no_version_comment(self):
        """Script without version comment — should still parse."""
        code = 'indicator("No Version")\nplot(close)'
        ir = parse_pine(code)
        # May produce error or default to v5 — either is fine
        assert ir is not None

    def test_whitespace_only(self):
        code = "   \n\n   "
        ir = parse_pine(code)
        assert len(ir.plots) == 0

    def test_comment_only(self):
        code = "// This is a comment\n// Another comment"
        ir = parse_pine(code)
        assert len(ir.plots) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
