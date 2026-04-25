# -*- coding: utf-8 -*-
"""minishare API 客户端封装.

封装 minishare Python SDK，提供字段映射、代码格式转换、重试机制，
使 API 返回的数据可直接写入本地 SQLite/MySQL 数据库。

Usage:
    from tdx_core.minishare_client import MinishareClient

    client = MinishareClient()          # token 从 MINISHARE_TOKEN 环境变量读取
    df = client.get_snapshot(["600519", "000001"])
    # df 列名已与本地数据库对齐: code, trade_date, open_val, high_val, ...
"""
from __future__ import annotations

import logging
import os
import time
from datetime import date
from typing import List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

_ms = None  # lazy-imported in MinishareClient.__init__


def _try_import_minishare():
    """Try to import minishare module; return None if not installed."""
    try:
        import minishare
        return minishare
    except ImportError:
        return None


# ─── 常量 ───────────────────────────────────────────────────────────────────

_API_BATCH_LIMIT = 300          # rt_k_ms 单次最多 300 支
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF = 2.0            # 指数退避基数（秒）

# 6 位 code → 市场后缀
_SUFFIX_MAP = {
    "6": ".SH",
    "0": ".SZ",
    "3": ".SZ",
    "9": ".BJ",
}

# API 字段 → 本地 DB 字段
_FIELD_MAP = {
    "open": "open_val",
    "high": "high_val",
    "low": "low_val",
    "close": "close_val",
    "vol": "volume",
}

# 本地 DB 需要的字段
_DB_COLUMNS = [
    "code", "trade_date", "open_val", "high_val", "low_val",
    "close_val", "volume", "amount",
]


class MinishareError(Exception):
    """minishare API 相关错误."""
    pass


class MinishareClient:
    """minishare API 客户端.

    Args:
        token: API 授权码。None 时自动读取环境变量 ``MINISHARE_TOKEN``。
    """

    def __init__(self, token: Optional[str] = None):
        global _ms
        if _ms is None:
            _ms = _try_import_minishare()
        if _ms is None:
            raise MinishareError(
                "minishare SDK 未安装。请执行: pip install minishare"
            )
        self._token = token or os.getenv("MINISHARE_TOKEN", "")
        if not self._token:
            raise MinishareError(
                "缺少 minishare API token。"
                "请设置环境变量 MINISHARE_TOKEN，"
                "或在构造函数中传入 token=..."
            )
        self._api = _ms.pro_api(self._token)

    # ─── 公开 API ─────────────────────────────────────────────────────────────

    def get_snapshot(self, codes: List[str]) -> pd.DataFrame:
        """获取 A 股实时日线快照.

        Args:
            codes: 6 位纯数字代码列表，如 ["600519", "000001"]
        Returns:
            标准化 DataFrame，列名与本地数据库对齐。
        """
        return self._fetch_batch(
            codes,
            api_method="rt_k_ms",
            limit=_API_BATCH_LIMIT,
        )

    def get_etf_snapshot(self, codes: List[str]) -> pd.DataFrame:
        """获取 ETF 实时日线快照."""
        return self._fetch_batch(
            codes,
            api_method="rt_etf_k_ms",
            limit=_API_BATCH_LIMIT,
        )

    def get_index_snapshot(self, codes: List[str]) -> pd.DataFrame:
        """获取指数实时日线快照."""
        return self._fetch_batch(
            codes,
            api_method="rt_idx_k",
            limit=_API_BATCH_LIMIT,
        )

    def get_intraday_snapshot(self, codes: List[str]) -> pd.DataFrame:
        """通过 rt_min_daily 分钟线聚合成当日日线.

        适用于仅有 rt_min 权限的 token，将当日分钟线聚合成
        open/high/low/close/volume/amount 日线格式后写入数据库。

        Args:
            codes: 6 位纯数字代码列表
        Returns:
            标准化 DataFrame，列名与本地数据库对齐。
        """
        if not codes:
            return pd.DataFrame(columns=_DB_COLUMNS)

        results: List[pd.DataFrame] = []
        for code in codes:
            ts_code = self._to_ts_code(code)
            try:
                df_min = self._call_with_retry("rt_min_daily", ts_code=ts_code)
            except MinishareError as exc:
                logger.warning("[%s] rt_min_daily 失败: %s", code, exc)
                continue

            if df_min is None or df_min.empty:
                continue

            # Aggregate minute bars → daily bar
            daily = self._aggregate_minute_to_daily(df_min, code)
            if daily is not None:
                results.append(daily)

        if not results:
            return pd.DataFrame(columns=_DB_COLUMNS)

        return pd.concat(results, ignore_index=True)

    @staticmethod
    def _aggregate_minute_to_daily(df_min: pd.DataFrame, code: str) -> Optional[pd.DataFrame]:
        """将一只股票的分钟线 DataFrame 聚合成单条日线."""
        df = df_min.copy()
        for col in ["open", "high", "low", "close", "vol", "amount"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        if df.empty or df["open"].isna().all():
            return None

        today = date.today().strftime("%Y-%m-%d")
        return pd.DataFrame([{
            "code": code,
            "trade_date": today,
            "open_val": float(df["open"].iloc[0]),
            "high_val": float(df["high"].max()),
            "low_val": float(df["low"].min()),
            "close_val": float(df["close"].iloc[-1]),
            "volume": int(df["vol"].sum()),
            "amount": float(df["amount"].sum()),
        }])

    # ─── 内部方法 ─────────────────────────────────────────────────────────────

    def _fetch_batch(
        self,
        codes: List[str],
        api_method: str,
        limit: int,
    ) -> pd.DataFrame:
        """分批拉取并合并结果."""
        if not codes:
            return pd.DataFrame(columns=_DB_COLUMNS)

        ts_codes = [self._to_ts_code(c) for c in codes]
        batches = [
            ts_codes[i:i + limit]
            for i in range(0, len(ts_codes), limit)
        ]

        results: List[pd.DataFrame] = []
        for idx, batch in enumerate(batches, 1):
            logger.info("[%s] 拉取第 %d/%d 批，共 %d 支",
                        api_method, idx, len(batches), len(batch))
            ts_code_str = ",".join(batch)
            df = self._call_with_retry(api_method, ts_code=ts_code_str)
            if df is not None and not df.empty:
                results.append(df)

        if not results:
            return pd.DataFrame(columns=_DB_COLUMNS)

        combined = pd.concat(results, ignore_index=True)
        return self._to_db_schema(combined)

    def _call_with_retry(self, method: str, **kwargs) -> Optional[pd.DataFrame]:
        """带重试的 API 调用."""
        api_fn = getattr(self._api, method, None)
        if api_fn is None:
            raise MinishareError(f"API 方法不存在: {method}")

        for attempt in range(1, _RETRY_ATTEMPTS + 1):
            try:
                return api_fn(**kwargs)
            except Exception as exc:
                logger.warning("[%s] 第 %d 次调用失败: %s", method, attempt, exc)
                if attempt < _RETRY_ATTEMPTS:
                    sleep_sec = _RETRY_BACKOFF ** attempt
                    logger.info("[%s] 等待 %.1f 秒后重试...", method, sleep_sec)
                    time.sleep(sleep_sec)
                else:
                    logger.error("[%s] 重试耗尽，放弃调用", method)
                    raise MinishareError(
                        f"minishare API '{method}' 调用失败: {exc}"
                    ) from exc
        return None  # unreachable

    # ─── 字段 / 代码映射 ──────────────────────────────────────────────────────

    @staticmethod
    def _to_ts_code(code: str) -> str:
        """把 6 位纯数字代码转成 API 需要的后缀格式.

        Examples:
            600519 → 600519.SH
            000001 → 000001.SZ
            688008 → 688008.SH
            900901 → 900901.BJ
        """
        code = code.strip()
        if len(code) != 6 or not code.isdigit():
            raise MinishareError(f"非法股票代码格式: {code!r} (应为 6 位数字)")
        suffix = _SUFFIX_MAP.get(code[0], ".SH")
        return f"{code}{suffix}"

    @staticmethod
    def _to_db_schema(df: pd.DataFrame) -> pd.DataFrame:
        """把 API 返回的 DataFrame 转成本地数据库格式.

        输入列名（来自 API）:
            ts_code, name, pre_close, high, open, low, close, vol, amount, ...
        输出列名（本地 DB）:
            code, trade_date, open_val, high_val, low_val, close_val, volume, amount
        """
        if df is None or df.empty:
            return pd.DataFrame(columns=_DB_COLUMNS)

        df = df.copy()

        # 提取纯数字 code
        if "ts_code" in df.columns:
            df["code"] = df["ts_code"].astype(str).str.split(".").str[0]
        else:
            logger.warning("API 返回缺少 ts_code 列，无法提取 code")
            df["code"] = ""

        # 增加 trade_date（当天）
        today = date.today().strftime("%Y-%m-%d")
        df["trade_date"] = today

        # 重命名列
        for old, new in _FIELD_MAP.items():
            if old in df.columns:
                df = df.rename(columns={old: new})

        # 确保数值类型
        for col in ["open_val", "high_val", "low_val", "close_val", "volume", "amount"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # 选择本地 DB 需要的列
        available = [c for c in _DB_COLUMNS if c in df.columns]
        missing = set(_DB_COLUMNS) - set(available)
        if missing:
            logger.warning("字段缺失，将填充 NaN: %s", missing)
            for col in missing:
                df[col] = pd.NA

        return df[_DB_COLUMNS].copy()
