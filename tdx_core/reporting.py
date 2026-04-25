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
