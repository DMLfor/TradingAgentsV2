"""TdxIndicatorAnalyzer 单元测试"""
import pandas as pd
import pytest

from tdx_core.analyzer import (
    TdxIndicatorAnalyzer,
    INDICATOR_PROFILES,
    _cross_above,
    _cross_below,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_query():
    """Return a mock TdxQuery that serves synthetic daily data."""
    class MockQuery:
        def __init__(self, data_map):
            self._data = data_map

        def get_daily(self, code, start_date=None, end_date=None):
            df = self._data.get(code)
            if df is None:
                return pd.DataFrame()
            # Apply date filter if given
            if start_date:
                df = df[df["trade_date"] >= start_date]
            if end_date:
                df = df[df["trade_date"] <= end_date]
            return df.copy()

    import numpy as np

    # Build deterministic synthetic data for two stocks (150 bars for macd/ichimoku)
    n = 150
    dates = pd.date_range("2023-06-01", periods=n, freq="B").astype(str)

    # Stock A: trending up then down
    close_a = 10.0 + np.linspace(0, 5, n) + np.sin(np.linspace(0, 4 * np.pi, n)) * 2
    df_a = pd.DataFrame({
        "code": "000001",
        "trade_date": dates,
        "open_val": close_a - 0.1,
        "high_val": close_a + 0.2,
        "low_val": close_a - 0.2,
        "close_val": close_a,
        "volume": 1000,
        "amount": 10000,
    })

    # Stock B: flat with noise
    close_b = 20.0 + np.random.default_rng(42).random(n) * 2 - 1
    df_b = pd.DataFrame({
        "code": "000002",
        "trade_date": dates,
        "open_val": close_b - 0.1,
        "high_val": close_b + 0.2,
        "low_val": close_b - 0.2,
        "close_val": close_b,
        "volume": 2000,
        "amount": 40000,
    })

    return MockQuery({"000001": df_a, "000002": df_b, "999999": pd.DataFrame()})


@pytest.fixture
def analyzer(mock_query):
    return TdxIndicatorAnalyzer(mock_query)


# ---------------------------------------------------------------------------
# Introspection tests
# ---------------------------------------------------------------------------


class TestIntrospection:
    def test_available_indicators(self, analyzer):
        names = analyzer.available_indicators()
        assert "macd" in names
        assert "rsi" in names
        assert "bollinger" in names

    def test_available_signals(self, analyzer):
        signals = analyzer.available_signals("macd")
        assert "golden_cross" in signals
        assert "death_cross" in signals

    def test_available_signals_unknown_indicator(self, analyzer):
        with pytest.raises(ValueError):
            analyzer.available_signals("not_an_indicator")


# ---------------------------------------------------------------------------
# Scan tests
# ---------------------------------------------------------------------------


class TestScan:
    def test_scan_rsi(self, analyzer):
        df = analyzer.scan(["000001", "000002"], indicator="rsi", params={"period": 14})
        assert not df.empty
        assert "code" in df.columns
        assert "rsi_14" in df.columns
        assert "latest_date" in df.columns
        assert len(df) == 2

    def test_scan_empty_universe(self, analyzer):
        df = analyzer.scan([], indicator="rsi")
        assert df.empty

    def test_scan_missing_stock(self, analyzer):
        df = analyzer.scan(["999999"], indicator="rsi")
        assert df.empty

    def test_scan_macd(self, analyzer):
        df = analyzer.scan(["000001"], indicator="macd")
        assert not df.empty
        assert "macd" in df.columns
        assert "macd_signal" in df.columns

    def test_scan_active_signals(self, analyzer):
        # With 30 bars of synthetic data there should be some active signals
        df = analyzer.scan(["000001", "000002"], indicator="macd")
        assert "active_signals" in df.columns


# ---------------------------------------------------------------------------
# Find signals tests
# ---------------------------------------------------------------------------


class TestFindSignals:
    def test_find_macd_golden_cross(self, analyzer):
        df = analyzer.find_signals(
            ["000001", "000002"],
            indicator="macd",
            signal_type="golden_cross",
        )
        # Synthetic data likely has at least one crossover
        assert isinstance(df, pd.DataFrame)

    def test_find_rsi_oversold(self, analyzer):
        df = analyzer.find_signals(
            ["000001"],
            indicator="rsi",
            signal_type="oversold",
            params={"period": 14},
        )
        assert isinstance(df, pd.DataFrame)

    def test_find_unknown_signal(self, analyzer):
        with pytest.raises(ValueError):
            analyzer.find_signals(
                ["000001"],
                indicator="macd",
                signal_type="not_a_signal",
            )

    def test_find_signals_no_data(self, analyzer):
        df = analyzer.find_signals(
            ["999999"],
            indicator="macd",
            signal_type="golden_cross",
        )
        assert df.empty


# ---------------------------------------------------------------------------
# Backtest tests
# ---------------------------------------------------------------------------


class TestBacktest:
    def test_backtest_macd_golden_cross(self, analyzer):
        report = analyzer.backtest(
            ["000001", "000002"],
            indicator="macd",
            signal_type="golden_cross",
            hold_days=3,
        )
        assert "summary" in report
        assert "detail" in report
        summary = report["summary"]
        assert isinstance(summary["total_signals"], int)
        if summary["total_signals"] > 0:
            assert isinstance(summary["win_rate"], float)
            assert isinstance(summary["avg_return"], float)

    def test_backtest_no_signals(self, analyzer):
        report = analyzer.backtest(
            ["999999"],
            indicator="rsi",
            signal_type="oversold",
            hold_days=5,
        )
        assert report["summary"]["total_signals"] == 0
        assert report["detail"].empty

    def test_backtest_detail_columns(self, analyzer):
        report = analyzer.backtest(
            ["000001"],
            indicator="macd",
            signal_type="golden_cross",
            hold_days=5,
        )
        if not report["detail"].empty:
            cols = set(report["detail"].columns)
            assert {"code", "buy_date", "sell_date", "buy_price", "sell_price", "return_pct"}.issubset(cols)


# ---------------------------------------------------------------------------
# Rank tests
# ---------------------------------------------------------------------------


class TestRank:
    def test_rank_rsi(self, analyzer):
        df = analyzer.rank(
            ["000001", "000002"],
            indicator="rsi",
            params={"period": 14},
            ascending=True,
        )
        assert not df.empty
        assert "rank" in df.columns
        assert df["rank"].iloc[0] == 1

    def test_rank_empty_universe(self, analyzer):
        df = analyzer.rank([], indicator="rsi")
        assert df.empty

    def test_rank_invalid_column(self, analyzer):
        with pytest.raises(ValueError):
            analyzer.rank(
                ["000001"],
                indicator="rsi",
                column="not_a_column",
            )


# ---------------------------------------------------------------------------
# Signal detector utility tests
# ---------------------------------------------------------------------------


class TestSignalUtilities:
    def test_cross_above(self):
        a = pd.Series([1, 2, 3, 2, 1])
        b = pd.Series([2, 2, 2, 2, 2])
        result = _cross_above(a, b)
        expected = pd.Series([False, False, True, False, False])
        assert (result == expected).all()

    def test_cross_below(self):
        a = pd.Series([3, 3, 1, 1, 3])
        b = pd.Series([2, 2, 2, 2, 2])
        result = _cross_below(a, b)
        expected = pd.Series([False, False, True, False, False])
        assert (result == expected).all()


# ---------------------------------------------------------------------------
# Profile registry completeness tests
# ---------------------------------------------------------------------------


class TestProfileRegistry:
    def test_all_profiles_have_signals(self):
        for name, profile in INDICATOR_PROFILES.items():
            assert profile.name == name
            assert profile.signals is not None
            assert profile.min_bars > 0

    def test_all_profiles_columns_callable(self):
        for name, profile in INDICATOR_PROFILES.items():
            cols = profile.get_columns({})
            assert isinstance(cols, list)
