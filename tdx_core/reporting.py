"""Unified report generation and output management for the project.

All reports are saved under `results/` with a structured directory layout:
    results/
    ├── README.md
    ├── index.md
    ├── backtest/YYYY-MM-DD/<strategy>/report.md
    ├── analysis/YYYY-MM-DD/<code>/report.md
    ├── ranking/YYYY-MM-DD/<name>.md
    └── tracker/<code>/<date>_*.md
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd


def _safe_name(name: str) -> str:
    """Convert a name to filesystem-safe ASCII."""
    s = name.strip().lower()
    # Replace common Chinese punctuation and special chars
    for ch in " \t/\\:*?\"<>|+=-.,;!@#$%^&()[]{}~`":
        s = s.replace(ch, "_")
    # Remove non-ascii
    s = s.encode("ascii", "ignore").decode("ascii")
    # Collapse underscores
    while "__" in s:
        s = s.replace("__", "_")
    return s.rstrip("_") or "unknown"


class ReportManager:
    """Manage structured report output under `results/`."""

    def __init__(self, base_dir: str = "results"):
        self.base = Path(base_dir)
        self.base.mkdir(exist_ok=True)
        for sub in ("backtest", "analysis", "ranking", "tracker"):
            (self.base / sub).mkdir(exist_ok=True)

    # ──────────────────────────────────────────────────────────────
    # Backtest reports
    # ──────────────────────────────────────────────────────────────

    def save_backtest_report(
        self,
        result,
        strategy_name: str,
        code: str,
        code_name: str = "",
        benchmark_code: str = "",
        start_date: str = "",
        end_date: str = "",
        strategy_id: str = "",
    ) -> Path:
        """Save a full backtest report as Markdown + JSON + CSV."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        dir_name = _safe_name(strategy_id) if strategy_id else _safe_name(strategy_name)
        dir_path = self.base / "backtest" / date_str / dir_name
        dir_path.mkdir(parents=True, exist_ok=True)

        # Metrics dict (JSON-safe)
        metrics = result.metrics.to_dict()

        # ASCII chart text
        ascii_chart = ""
        try:
            from scripts.strategy_backtest import _plot_nav
            import io, sys
            old_stdout = sys.stdout
            sys.stdout = buffer = io.StringIO()
            _plot_nav(result, strategy_name, start_date, end_date)
            sys.stdout = old_stdout
            ascii_chart = buffer.getvalue()
        except Exception:
            ascii_chart = "（ASCII 图生成失败）"

        # Trade log
        trades_df = result.trade_log()
        if not trades_df.empty:
            trades_md = trades_df.head(20).to_markdown(index=False)
        else:
            trades_md = "无交易记录"

        # Build Markdown
        front_matter = {
            "type": "backtest",
            "date": date_str,
            "strategy": strategy_name,
            "code": code,
            "name": code_name or code,
            "period": f"{start_date} ~ {end_date}",
            "benchmark": benchmark_code,
            "total_return_pct": metrics.get("total_return_pct"),
            "max_drawdown_pct": metrics.get("max_drawdown_pct"),
            "sharpe_ratio": metrics.get("sharpe_ratio"),
            "win_rate": metrics.get("win_rate"),
            "total_trades": metrics.get("total_trades"),
        }

        md_lines = [
            "---",
            json.dumps(front_matter, ensure_ascii=False, indent=2),
            "---",
            "",
            f"# {code_name or code} ({code}) — {strategy_name} 回测报告",
            "",
            "## 执行摘要",
            f"- **策略**: {strategy_name}",
            f"- **标的**: {code_name or code} ({code})",
            f"- **回测区间**: {start_date} ~ {end_date} ({result.metrics.trading_days} 个交易日)",
            f"- **基准**: {benchmark_code or '无'}",
            "",
            "## 绩效指标",
            "",
            self._metrics_table(metrics),
            "",
            "## ASCII 资金曲线",
            "",
            "```",
            ascii_chart,
            "```",
            "",
            "## 最近交易记录 (前20笔)",
            "",
            trades_md,
            "",
            "## 结论",
            "",
            "（待补充）",
        ]

        report_path = dir_path / "report.md"
        report_path.write_text("\n".join(md_lines), encoding="utf-8")

        # Save JSON
        json_path = dir_path / "metrics.json"
        json_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

        # Save CSVs
        if not trades_df.empty:
            trades_df.to_csv(dir_path / "trades.csv", index=False, encoding="utf-8-sig")
        nav_df = result.nav_df()
        if not nav_df.empty:
            nav_df.to_csv(dir_path / "nav.csv", index=False, encoding="utf-8-sig")

        return report_path

    # ──────────────────────────────────────────────────────────────
    # Batch summary
    # ──────────────────────────────────────────────────────────────

    def save_batch_summary(self, rows: list[dict], code: str, code_name: str = "", benchmark: str = "", start_date: str = "", end_date: str = "") -> Path:
        """Save a batch backtest comparison table."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        dir_path = self.base / "backtest" / date_str
        dir_path.mkdir(parents=True, exist_ok=True)

        df = pd.DataFrame(rows)
        # Sort by sharpe desc
        if "sharpe_ratio" in df.columns:
            df = df.sort_values("sharpe_ratio", ascending=False)

        md_lines = [
            "---",
            json.dumps({
                "type": "batch_summary",
                "date": date_str,
                "code": code,
                "name": code_name or code,
                "period": f"{start_date} ~ {end_date}",
                "benchmark": benchmark,
                "num_strategies": len(rows),
            }, ensure_ascii=False, indent=2),
            "---",
            "",
            f"# {code_name or code} ({code}) — 策略批量回测汇总",
            "",
            f"**回测区间**: {start_date} ~ {end_date}  ",
            f"**基准**: {benchmark or '无'}  ",
            f"**策略数量**: {len(rows)}",
            "",
            "## 排名表（按夏普比率降序）",
            "",
            df.to_markdown(index=False),
            "",
            "## 最优策略",
            "",
        ]

        if not df.empty:
            best = df.iloc[0]
            tr = best.get('total_return_pct')
            dd = best.get('max_drawdown_pct')
            sr = best.get('sharpe_ratio')
            wr = best.get('win_rate')
            md_lines.extend([
                f"- **策略**: {best.get('strategy', '')}",
                f"- **总收益率**: {tr:+.2f}%" if tr is not None else "- **总收益率**: N/A",
                f"- **最大回撤**: {dd:.2f}%" if dd is not None else "- **最大回撤**: N/A",
                f"- **夏普比率**: {sr:.2f}" if sr is not None else "- **夏普比率**: N/A",
                f"- **胜率**: {wr:.1f}%" if wr is not None else "- **胜率**: N/A",
                f"- **交易次数**: {best.get('total_trades', 0)}",
            ])

        md_lines.append("")

        path = dir_path / "batch_summary.md"
        path.write_text("\n".join(md_lines), encoding="utf-8")

        # Also save CSV
        df.to_csv(dir_path / "batch_summary.csv", index=False, encoding="utf-8-sig")

        return path

    # ──────────────────────────────────────────────────────────────
    # Analysis / K-line reports
    # ──────────────────────────────────────────────────────────────

    def save_analysis_report(
        self,
        code: str,
        code_name: str,
        content: str,
        report_type: str = "kline",
    ) -> Path:
        """Save a single-stock analysis report (e.g. K-line chart)."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        dir_path = self.base / "analysis" / date_str / _safe_name(code)
        dir_path.mkdir(parents=True, exist_ok=True)

        front_matter = {
            "type": report_type,
            "date": date_str,
            "code": code,
            "name": code_name,
        }

        md_lines = [
            "---",
            json.dumps(front_matter, ensure_ascii=False, indent=2),
            "---",
            "",
            f"# {code_name} ({code}) — {report_type} 分析报告",
            "",
            content,
        ]

        path = dir_path / "report.md"
        path.write_text("\n".join(md_lines), encoding="utf-8")
        return path

    # ──────────────────────────────────────────────────────────────
    # Daily review reports
    # ──────────────────────────────────────────────────────────────

    def save_review_report(self, data: dict) -> Path:
        """Save a daily market review report as Markdown."""
        date_str = data.get("date", datetime.now().strftime("%Y-%m-%d"))
        dir_path = self.base / "review" / date_str
        dir_path.mkdir(parents=True, exist_ok=True)

        front_matter = {
            "type": "daily_review",
            "date": date_str,
            "sentiment": data.get("sentiment", {}).get("sentiment", "未知"),
        }

        md_lines = [
            "---",
            json.dumps(front_matter, ensure_ascii=False, indent=2),
            "---",
            "",
            f"# A股每日技术复盘报告 — {date_str}",
            "",
            "## 一、大盘环境",
            "",
            self._overview_table(data.get("overview", [])),
            "",
            "## 二、市场风格",
            "",
            self._style_text(data.get("style", {})),
            "",
            "## 三、板块热力",
            "",
            "### 领涨 TOP5",
            "",
            self._sector_table(data.get("top5")),
            "",
            "### 领跌 TOP5",
            "",
            self._sector_table(data.get("bottom5")),
            "",
            "## 四、市场情绪",
            "",
            self._sentiment_text(data.get("sentiment", {})),
            "",
            "## 五、趋势评分",
            "",
            self._trend_score_text(data.get("trend_score", {})),
            "",
            "## 六、量价分析",
            "",
            self._volume_price_text(data.get("volume_price", {})),
            "",
            "## 七、明日前瞻",
            "",
            self._outlook_text(data.get("outlook", {})),
            "",
            "## 八、ETF 策略日报",
            "",
            self._etf_text(data.get("etf", [])),
            "",
            "## 九、信号雷达",
            "",
            self._signal_table(data.get("signals", [])),
            "",
            "## 十、回撤选股",
            "",
            self._pick_table(data.get("picks", [])),
            "",
            "## 十一、次日交易计划",
            "",
            data.get("action_plan", "（无）"),
            "",
            "---",
            "*注: 本报告基于技术分析与历史数据。龙虎榜、消息面、北向资金等维度需外部数据源补充。*",
        ]

        report_path = dir_path / "daily_review.md"
        report_path.write_text("\n".join(md_lines), encoding="utf-8")
        return report_path

    # ──────────────────────────────────────────────────────────────
    # Index update
    # ──────────────────────────────────────────────────────────────

    def update_index(self):
        """Scan results/ and regenerate index.md."""
        lines = ["# 报告索引", ""]

        # Backtest
        bt_dir = self.base / "backtest"
        if bt_dir.exists():
            dates = sorted(bt_dir.iterdir(), reverse=True)
            for d in dates:
                if not d.is_dir():
                    continue
                lines.append(f"## {d.name} — 回测")
                summary = d / "batch_summary.md"
                if summary.exists():
                    lines.append(f"- [批量回测汇总](backtest/{d.name}/batch_summary.md)")
                for sub in sorted(d.iterdir()):
                    if sub.is_dir() and (sub / "report.md").exists():
                        lines.append(f"  - [{sub.name}](backtest/{d.name}/{sub.name}/report.md)")
                lines.append("")

        # Analysis
        ana_dir = self.base / "analysis"
        if ana_dir.exists():
            dates = sorted(ana_dir.iterdir(), reverse=True)
            for d in dates:
                if not d.is_dir():
                    continue
                lines.append(f"## {d.name} — 个股分析")
                for sub in sorted(d.iterdir()):
                    if sub.is_dir() and (sub / "report.md").exists():
                        lines.append(f"- [{sub.name}](analysis/{d.name}/{sub.name}/report.md)")
                lines.append("")

        # Ranking
        rank_dir = self.base / "ranking"
        if rank_dir.exists():
            dates = sorted(rank_dir.iterdir(), reverse=True)
            for d in dates:
                if not d.is_dir():
                    continue
                lines.append(f"## {d.name} — 排行/筛选")
                for f in sorted(d.glob("*.md")):
                    lines.append(f"- [{f.stem}](ranking/{d.name}/{f.name})")
                lines.append("")

        # Review
        review_dir = self.base / "review"
        if review_dir.exists():
            dates = sorted(review_dir.iterdir(), reverse=True)
            for d in dates:
                if not d.is_dir():
                    continue
                report = d / "daily_review.md"
                if report.exists():
                    lines.append(f"## {d.name} — 每日复盘")
                    lines.append(f"- [每日技术复盘](review/{d.name}/daily_review.md)")
                    lines.append("")

        index_path = self.base / "index.md"
        index_path.write_text("\n".join(lines), encoding="utf-8")
        return index_path

    # ──────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _metrics_table(metrics: dict) -> str:
        """Convert metrics dict to a Markdown table."""
        rows = []
        mapping = {
            "total_return_pct": "总收益率",
            "annualized_return": "年化收益率",
            "benchmark_return": "基准收益率",
            "max_drawdown_pct": "最大回撤",
            "volatility_annual": "年化波动率",
            "sharpe_ratio": "夏普比率",
            "sortino_ratio": "索提诺比率",
            "calmar_ratio": "卡玛比率",
            "alpha": "Alpha",
            "beta": "Beta",
            "total_trades": "总交易次数",
            "win_trades": "盈利次数",
            "loss_trades": "亏损次数",
            "win_rate": "胜率",
            "avg_return_per_trade": "平均收益",
            "avg_win": "平均盈利",
            "avg_loss": "平均亏损",
            "profit_factor": "盈亏比",
            "largest_win": "最大单笔盈利",
            "largest_loss": "最大单笔亏损",
            "trading_days": "交易日数",
        }
        for k, label in mapping.items():
            v = metrics.get(k)
            if v is None:
                continue
            if "pct" in k or "rate" in k and k != "win_rate":
                rows.append(f"| {label} | {v:+.2f}% |")
            elif k == "win_rate":
                rows.append(f"| {label} | {v:.1f}% |")
            elif isinstance(v, float):
                rows.append(f"| {label} | {v:.2f} |")
            else:
                rows.append(f"| {label} | {v} |")
        return "| 指标 | 数值 |\n|------|------|\n" + "\n".join(rows)


    @staticmethod
    def _overview_table(overview: list[dict]) -> str:
        if not overview:
            return "暂无数据"
        rows = []
        for item in overview:
            change_str = f"{item['change_pct']:+.2f}%"
            if item.get("data_anomaly"):
                change_str += " [数据异常]"
            rows.append(
                f"| {item['name']} | {item['close']:.2f} | "
                f"{change_str} | {item['vol_ratio_5']:.2f} | "
                f"{item['ma_state']} | {item['macd_state']} | {item['rsi']:.1f} |"
            )
        return (
            "| 指数 | 收盘价 | 涨跌 | 量比 | 均线状态 | MACD | RSI |\n"
            "|------|--------|------|------|----------|------|-----|\n"
            + "\n".join(rows)
        )

    @staticmethod
    def _style_text(style: dict) -> str:
        large = style.get("large_return")
        small = style.get("small_return")
        diff = style.get("diff")
        lines = [f"- **风格判断**: {style.get('style', '未知')}"]
        if large is not None:
            lines.append(f"- **大盘(沪深300) 20日收益**: {large:+.2f}%")
        if small is not None:
            lines.append(f"- **小盘(中证1000) 20日收益**: {small:+.2f}%")
        if diff is not None:
            lines.append(f"- **相对强弱差**: {diff:+.2f}%")
        return "\n".join(lines)

    @staticmethod
    def _sector_table(df) -> str:
        if df is None or df.empty:
            return "暂无数据"
        rows = []
        for _, row in df.iterrows():
            rows.append(
                f"| {row['sector']} | {row['avg_change_pct']:+.2f}% | "
                f"{row.get('repr', '')} |"
            )
        return (
            "| 板块 | 平均涨跌 | 代表个股 |\n"
            "|------|----------|----------|\n"
            + "\n".join(rows)
        )

    @staticmethod
    def _sentiment_text(sentiment: dict) -> str:
        if "error" in sentiment:
            return f"[错误] {sentiment['error']}"
        lines = [
            f"- **全市场家数**: 共 {sentiment.get('total', 0)} 只",
            f"- **上涨/下跌/平盘**: {sentiment.get('up', 0)} / {sentiment.get('down', 0)} / {sentiment.get('flat', 0)}",
            f"- **涨停(近似)**: {sentiment.get('limit_up', 0)} 家",
            f"- **跌停(近似)**: {sentiment.get('limit_down', 0)} 家",
            f"- **涨跌停比**: {sentiment.get('limit_up', 0) / max(sentiment.get('limit_down', 1), 1):.2f}",
            f"- **情绪档位**: {sentiment.get('sentiment', '未知')} — {sentiment.get('advice', '')}",
        ]

        # 趋势信息
        trend = sentiment.get("trend", "")
        stage = sentiment.get("stage", "")
        if trend:
            lines.append(f"- **情绪趋势**: {trend}（{stage}）")

        history = sentiment.get("trend_history", [])
        if history:
            parts = []
            for h in history:
                date_short = str(h.get("date", ""))[-5:]
                up_r = h.get("up_ratio", 0)
                limit_up = h.get("limit_up", 0)
                parts.append(f"{date_short} {up_r:.1%}({limit_up}涨)")
            lines.append("- **近5日情绪轨迹**: " + " → ".join(parts))

        # 新增：趋势评分 & 量价摘要（在情绪板块中简要展示）
        trend_stage = sentiment.get("trend_stage", "")
        trend_score = sentiment.get("trend_score", 0)
        if trend_stage:
            lines.append(f"- **大盘趋势**: {trend_stage} (评分: {trend_score})")
        volume_state = sentiment.get("volume_state", "")
        money_flow = sentiment.get("money_flow", "")
        if volume_state:
            lines.append(f"- **量能/资金**: {volume_state} | {money_flow}")
        vp_notes = sentiment.get("vp_notes", [])
        trend_notes = sentiment.get("trend_notes", [])
        all_notes = trend_notes + vp_notes
        if all_notes:
            lines.append(f"- **修正提示**: {'；'.join(all_notes)}")

        return "\n".join(lines)

    @staticmethod
    def _trend_score_text(trend_score: dict) -> str:
        if not trend_score or "stage" not in trend_score:
            return "暂无数据"
        lines = [
            f"- **趋势档位**: {trend_score.get('stage', '未知')}",
            f"- **综合评分**: {trend_score.get('trend_score', 0)} (范围: -100~+100)",
            f"- **即时技术面得分**: {trend_score.get('instant_score', 0)}",
            f"- **历史位置修正**: {trend_score.get('position_penalty', 0)}",
            f"- **连涨连跌修正**: {trend_score.get('consecutive_score', 0)}",
            f"- **情绪分位修正**: {trend_score.get('emotion_hist_score', 0)}",
            "",
            "**评分说明**:",
            "- ≥+40 强多头 | +10~+40 弱多头 | -10~+10 震荡 | -40~-10 弱空头 | ≤-40 强空头",
            "- 即时技术面: 均线+MACD+RSI 加权评分",
            "- 历史位置修正: 价格处于60日高低点分位的修正（高位减分/低位加分）",
            "- 连涨连跌修正: 连续5天以上同向运行的修正（过热减分/超跌加分）",
            "- 情绪分位修正: 当日上涨家数占比在近30日的百分位修正",
        ]
        return "\n".join(lines)

    @staticmethod
    def _volume_price_text(vp: dict) -> str:
        if not vp:
            return "暂无数据"
        lines = [
            f"- **量能状态**: {vp.get('volume_state', '未知')} (较5日均值: {vp.get('volume_change_pct', 0):+.1f}%)",
            f"- **资金流向**: {vp.get('money_flow', '未知')}",
            f"- **上涨股票成交额**: {vp.get('up_amount', 0):.1f} 亿元",
            f"- **下跌股票成交额**: {vp.get('down_amount', 0):.1f} 亿元",
            "",
            "**量价背离检测**:",
        ]
        for d in vp.get("divergence", ["无明显背离"]):
            lines.append(f"- {d}")
        return "\n".join(lines)

    @staticmethod
    def _outlook_text(outlook: dict) -> str:
        if not outlook:
            return "暂无数据"
        lines = [
            f"- **支撑位**: {outlook.get('support', '未知')}",
            f"- **压力位**: {outlook.get('resistance', '未知')}",
            f"- **关键观察位**: {outlook.get('key_level', '未知')}",
            "",
            "**情景推演**:",
        ]
        for sc in outlook.get("scenarios", []):
            lines.append(f"- **[{sc['label']}]** 概率{sc['prob']} — {sc['condition']} → **{sc['action']}**")
        watch = outlook.get("watch_points", [])
        if watch:
            lines.append("")
            lines.append("**明日观察要点**:")
            for wp in watch:
                lines.append(f"- {wp}")
        return "\n".join(lines)

    @staticmethod
    def _etf_text(etf_list: list[dict]) -> str:
        if not etf_list:
            return "暂无数据"
        lines = []
        for etf in etf_list:
            lines.append(f"### {etf['code']} ({etf['name']})")
            lines.append(f"- **趋势状态**: {etf['state_zh']} ({etf['state']})")
            lines.append(f"- **综合评分**: {etf['trend_score']}/10")
            lines.append(f"- **RSI(14)**: {etf['rsi']:.1f}")
            lines.append(f"- **布林带%B**: {etf['bb_pctb']:.3f}")
            lines.append(f"- **ATR%**: {etf['atr_pct']:.2f}%")
            if etf.get("vol_pct") is not None:
                lines.append(f"- **ATR 百分位**: {etf['vol_pct']}%")
            grid = etf.get("grid", {})
            if grid.get("buy_levels"):
                lines.append(f"- **买入网格**: {' / '.join(str(v) for v in grid['buy_levels'])}")
            if grid.get("sell_levels"):
                lines.append(f"- **卖出网格**: {' / '.join(str(v) for v in grid['sell_levels'])}")
            lines.append(f"- **网格说明**: {grid.get('note', '')}")
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _signal_table(signals: list[dict]) -> str:
        if not signals:
            return "暂无数据"
        rows = []
        for s in signals:
            rows.append(f"| {s['signal']} | {s['count']} | {s.get('repr', '')} |")
        return (
            "| 信号类型 | 触发数量 | 代表个股 |\n"
            "|----------|----------|----------|\n"
            + "\n".join(rows)
        )

    @staticmethod
    def _pick_table(picks: list[dict]) -> str:
        if not picks:
            return "今日无符合条件的标的"
        rows = []
        for p in picks:
            rows.append(
                f"| {p['code']} | {p['name']} | {p['total_score']:.0f} | "
                f"{p['entry_price']:.2f} | {p['stop_price']:.2f} | "
                f"{p['target_price']:.2f} | {p['risk_reward']:.2f} | {p['position_suggestion']} |"
            )
        return (
            "| 代码 | 名称 | 评分 | 买入价 | 止损 | 目标价 | 盈亏比 | 建议仓位 |\n"
            "|------|------|------|--------|------|--------|--------|----------|\n"
            + "\n".join(rows)
        )
