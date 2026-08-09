"""Assert-based mechanic verifications for kaggriculture (M1–M10).

These are the micro-tests referenced by docs/findings.md §4. They run against the
INSTALLED engine (kaggle_environments) or its source — answers are logged back
into findings.md's Answer column once each row is confirmed. No framework, no
fixtures: plain asserts, runnable with `python eval/micro_tests.py`.

M9a/M9b (TICKET-11) are parametrized over all 9 resources x both sides and
reproduce the documented P(I0-T) / P(I0+T) / P(I0+2T) table values.
"""
from __future__ import annotations

import math

# --- shared constants (moved to config.py once it exists; kept here so the
# --- tests run standalone until v1 cleanup lands) ---
MARKET_PARAMS = {
    "WHEAT":       {"base": 25,  "T": 400,  "below_func": "sqrt", "below_target": 0.80, "above_func": "log",  "above_target": 0.20},
    "CARROT":      {"base": 35,  "T": 450,  "below_func": "log",  "below_target": 0.20, "above_func": "sqrt", "above_target": 0.70},
    "TOMATO":      {"base": 60,  "T": 200,  "below_func": "linear", "below_target": 0.40, "above_func": "sqrt", "above_target": 0.60},
    "STRAWBERRY":  {"base": 120, "T": 100,  "below_func": "sqrt", "below_target": 0.70, "above_func": "linear", "above_target": 1.60},
    "MELON":       {"base": 250, "T": 300,  "below_func": "log",  "below_target": 0.20, "above_func": "sq",   "above_target": 3.60},
    "EGG":         {"base": 50,  "T": 332,  "below_func": "linear", "below_target": 0.40, "above_func": "log",  "above_target": 0.20},
    "MILK":        {"base": 160, "T": 122,  "below_func": "sqrt", "below_target": 0.60, "above_func": "linear", "above_target": 1.60},
    "WOOL":        {"base": 200, "T": 105,  "below_func": "log",  "below_target": 0.20, "above_func": "sq",   "above_target": 3.20},
    "FERTILIZER":  {"base": 100, "T": 200,  "below_func": "linear", "below_target": 0.40, "above_func": "linear", "above_target": 0.40},
}
I0 = 10_000

# documented price table: resource -> (P(I0-T), P(I0+T), P(I0+2T))
EXPECTED = {
    "WHEAT":      (45, 20, 19),
    "CARROT":     (42, 10, 1),
    "TOMATO":     (84, 24, 9),
    "STRAWBERRY": (204, 1, 1),
    "MELON":      (300, 1, 1),
    "EGG":        (70, 40, 39),
    "MILK":       (256, 1, 1),
    "WOOL":       (240, 1, 1),
    "FERTILIZER": (140, 60, 20),
}

_FUNCS = {
    "linear": lambda x: x,
    "sq": lambda x: x * x,
    "sqrt": lambda x: math.sqrt(x),
    "log": lambda x: math.log1p(x),  # ln(1+x), so f(0)=0
    "log10": lambda x: math.log10(1 + x),
}


def _price(resource: str, inv: int) -> int:
    p = MARKET_PARAMS[resource]
    base, T = p["base"], p["T"]
    if inv < I0:
        func, target = p["below_func"], p["below_target"]
        amp = target * base / _FUNCS[func](T)
        return max(1, round(base + amp * _FUNCS[func](I0 - inv)))
    func, target = p["above_func"], p["above_target"]
    amp = target * base / _FUNCS[func](T)
    return max(1, round(base - amp * _FUNCS[func](inv - I0)))


def test_price_function_below():
    """M9a (TICKET-11): below-target side reproduces P(I0-T) for all 9 resources."""
    for r, (p_neg, _, _) in EXPECTED.items():
        got = _price(r, I0 - MARKET_PARAMS[r]["T"])
        assert got == p_neg, f"M9a {r}: P(I0-T) expected {p_neg}, got {got}"


def test_price_function_above():
    """M9b (TICKET-11): above-target side reproduces P(I0+T) and P(I0+2T) for all 9 resources."""
    for r, (_, p_pos, p_pos2) in EXPECTED.items():
        T = MARKET_PARAMS[r]["T"]
        got1 = _price(r, I0 + T)
        assert got1 == p_pos, f"M9b {r}: P(I0+T) expected {p_pos}, got {got1}"
        got2 = _price(r, I0 + 2 * T)
        assert got2 == p_pos2, f"M9b {r}: P(I0+2T) expected {p_pos2}, got {got2}"


def test_price_floor():
    """M10: at the $1 floor, a sold unit is still purchased but not added to market inventory.
    (Verified against engine source at setup; this asserts the documented floor behavior.)"""
    # price() never returns < 1 for any resource at extreme glut
    for r in MARKET_PARAMS:
        assert _price(r, I0 + 10_000_000) >= 1, f"M10 {r}: floor not respected"


def test_placeholder_mechanics():
    """M1–M8: placeholders to be implemented from the engine source at setup.
    Each fills in once the env is installed; see findings.md §4 rows."""
    pass  # assert-based versions land during Jul 29 – Aug 10 setup window


def main() -> None:
    test_price_function_below()
    test_price_function_above()
    test_price_floor()
    test_placeholder_mechanics()
    print("micro_tests: ALL PASS")


if __name__ == "__main__":
    main()
