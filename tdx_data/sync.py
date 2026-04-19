"""增量同步引擎（多线程并行版 + 进度展示）"""
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

import pandas as pd

from .config import TdxConfig
from .db import TdxDatabase
from .models import FileInfo, SyncResult, TABLE_MAP
from .reader import TdxReader
from .scanner import TdxScanner

logger = logging.getLogger(__name__)


def _format_rows(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


class TdxSyncEngine:
    """通信达数据同步引擎

    支持：
    - full_import：首次全量导入（多线程并行读取）
    - incremental_sync：增量同步（mtime/size + 尾部追加）
    - sync_by_market：按市场同步

    并行策略：读取文件（CPU/IO 密集）用线程池并行，写入数据库串行。
    """

    def __init__(self, config: Optional[TdxConfig] = None):
        self.config = config or TdxConfig()
        self.reader = TdxReader(self.config)
        self.scanner = TdxScanner(self.config)
        self.db = TdxDatabase(self.config)
        self.max_workers = getattr(config, 'max_workers', 4) if config else 4

    def full_import(self, max_workers: int = 4) -> SyncResult:
        """全量导入（多线程并行，已导入文件自动跳过）

        利用文件注册表检测已导入的文件，只处理新增/变更的文件，
        支持重复执行——幂等安全。
        """
        start = time.time()
        all_files = self.scanner.scan_all()
        logger.info("Full import: found %d files, workers=%d", len(all_files), max_workers)

        # 利用文件注册表过滤已导入的文件
        known_files = self.db.get_file_registry()
        changes = self.scanner.detect_changes(known_files, all_files)
        to_process = changes["new"] + changes["modified"]
        skipped = len(changes.get("unchanged", []))

        if not to_process:
            logger.info("Full import: all %d files already synced, skipped=%d",
                        len(all_files), skipped)
            duration = time.time() - start
            result = SyncResult()
            self._log_sync("full_skip", result, duration)
            return result

        logger.info("Full import: new=%d, modified=%d, skipped=%d",
                    len(changes["new"]), len(changes["modified"]), skipped)

        new_set = {fi.file_path for fi in changes["new"]}
        result = self._process_files_parallel(
            to_process, max_workers=max_workers,
            append_only=True, new_files=new_set,
        )
        duration = time.time() - start
        self._log_sync("full", result, duration)
        return result

    def incremental_sync(self, markets: List[str] = None) -> Optional[SyncResult]:
        """增量同步"""
        start = time.time()

        if markets is None:
            markets = ["sh", "sz"]

        current_files = []
        for m in markets:
            current_files.extend(self.scanner.scan_market(m, "daily"))

        known_files = self.db.get_file_registry()
        changes = self.scanner.detect_changes(known_files, current_files)
        to_process = changes["new"] + changes["modified"]

        if not to_process:
            logger.info("No changes detected, sync skipped")
            return None

        logger.info(
            "Incremental: new=%d, modified=%d, processing...",
            len(changes["new"]), len(changes["modified"])
        )

        new_set = {fi.file_path for fi in changes["new"]}
        result = self._process_files(to_process, append_only=True,
                                     new_files=new_set)
        duration = time.time() - start
        self._log_sync("incremental", result, duration)
        return result

    def sync_by_market(self, market: str,
                       data_type: str = None,
                       max_workers: int = 4) -> SyncResult:
        """按市场同步（多线程并行，已导入文件自动跳过）"""
        start = time.time()
        files = self.scanner.scan_market(market, data_type)
        logger.info("Market sync %s: found %d files, workers=%d",
                    market, len(files), max_workers)

        known_files = self.db.get_file_registry()
        changes = self.scanner.detect_changes(known_files, files)
        to_process = changes["new"] + changes["modified"]

        if not to_process:
            logger.info("Market sync %s: all files already synced", market)
            duration = time.time() - start
            result = SyncResult()
            self._log_sync(f"market_{market}_skip", result, duration)
            return result

        logger.info("Market sync %s: new=%d, modified=%d, skipped=%d",
                    market, len(changes["new"]), len(changes["modified"]),
                    len(changes["unchanged"]))

        new_set = {fi.file_path for fi in changes["new"]}
        result = self._process_files_parallel(
            to_process, max_workers=max_workers,
            append_only=True, new_files=new_set,
        )
        duration = time.time() - start
        self._log_sync(f"market_{market}", result, duration)
        return result

    def _process_files_parallel(self, files: List[FileInfo],
                                max_workers: int = 4,
                                append_only: bool = False,
                                new_files: set = None) -> SyncResult:
        """并行读取文件，批量写入数据库

        策略：
        1. 用线程池并行读取 TDX 文件为 DataFrame
        2. 每个 DataFrame 先 reset_index 把 date 变为普通列
        3. 收集到一定数量后，合并为一个大 DataFrame
        4. 一次性批量 upsert 到数据库
        """
        total_read = 0
        total_written = 0
        total_failed = 0
        failed_files = []

        collect_size = max_workers * 4
        table_dfs: Dict[str, List[pd.DataFrame]] = {}

        total_files = len(files)
        files_done = 0
        start_time = time.time()

        def _print_progress():
            elapsed = time.time() - start_time
            speed = files_done / elapsed if elapsed > 0 else 0
            eta = (total_files - files_done) / speed if speed > 0 else 0
            sys.stdout.write(
                f"\r  Progress: {files_done}/{total_files} files "
                f"| Read: {_format_rows(total_read)} rows "
                f"| Written: {_format_rows(total_written)} rows "
                f"| Failed: {_format_rows(total_failed)} "
                f"| Elapsed: {elapsed:.0f}s "
                f"| ETA: {eta:.0f}s"
            )
            sys.stdout.flush()

        def read_one(fi: FileInfo) -> Optional[tuple]:
            for attempt in range(1, self.config.max_retries + 1):
                try:
                    is_new = new_files and fi.file_path in new_files
                    if append_only and not is_new:
                        df = self._read_file_append(fi)
                    else:
                        df = self._read_file(fi)
                    return (fi, df)
                except Exception as exc:
                    if attempt == self.config.max_retries:
                        logger.error("Read failed after %d attempts: %s - %s",
                                     attempt, fi.file_path, exc)
                        return (fi, None)
                    time.sleep(self.config.retry_delay * attempt)

        def flush_table(table: str):
            nonlocal total_read, total_written, total_failed, failed_files
            dfs = table_dfs.pop(table, [])
            if not dfs:
                return
            merged = pd.concat(dfs, ignore_index=True)
            try:
                written = self.db.upsert_dataframe(
                    merged, table=table, batch_size=self.config.batch_size
                )
                total_written += written
            except Exception as exc:
                logger.error("Batch write failed for %s: %s", table, exc)
                total_failed += len(merged)
                failed_files.append(f"batch:{table}")
            total_read += len(merged)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(read_one, fi): fi for fi in files}

            for future in as_completed(futures):
                fi = futures[future]
                try:
                    result = future.result()
                    if result is None:
                        total_failed += 1
                        failed_files.append(fi.file_path)
                        files_done += 1
                        _print_progress()
                        continue

                    _, df = result
                    if df is None or df.empty:
                        self.db.update_file_registry(fi, 0)
                        files_done += 1
                        _print_progress()
                        continue

                    table = TABLE_MAP.get(fi.data_type)
                    if not table:
                        files_done += 1
                        _print_progress()
                        continue

                    # reset_index 把 date 从索引变为普通列，避免 concat 丢失
                    df = df.reset_index()
                    table_dfs.setdefault(table, []).append(df)
                    self.db.update_file_registry(fi, len(df))
                    files_done += 1
                    _print_progress()

                    collected = sum(len(v) for v in table_dfs.values())
                    if collected >= collect_size:
                        for t in list(table_dfs.keys()):
                            flush_table(t)

                except Exception as exc:
                    total_failed += 1
                    failed_files.append(fi.file_path)
                    files_done += 1
                    _print_progress()
                    logger.error("Future error for %s: %s", fi.file_path, exc)

        # Flush 剩余
        for t in list(table_dfs.keys()):
            flush_table(t)

        # 最终进度行
        elapsed = time.time() - start_time
        sys.stdout.write(
            f"\n  Done: {total_files} files | Read: {_format_rows(total_read)} "
            f"| Written: {_format_rows(total_written)} "
            f"| Failed: {_format_rows(total_failed)} "
            f"| Duration: {elapsed:.1f}s\n"
        )
        sys.stdout.flush()

        return SyncResult(
            rows_read=total_read,
            rows_written=total_written,
            rows_failed=total_failed,
            failed_files=failed_files,
        )

    def _process_files(self, files: List[FileInfo],
                       append_only: bool = False,
                       new_files: set = None) -> SyncResult:
        """串行处理文件列表（增量同步用，文件少）"""
        total_read = 0
        total_written = 0
        total_failed = 0
        failed_files = []
        total_files = len(files)
        start_time = time.time()

        for idx, fi in enumerate(files, 1):
            for attempt in range(1, self.config.max_retries + 1):
                try:
                    is_new = new_files and fi.file_path in new_files
                    if append_only and not is_new:
                        df = self._read_file_append(fi)
                    else:
                        df = self._read_file(fi)

                    if df is None or df.empty:
                        self.db.update_file_registry(fi, 0)
                        break

                    rows_read = len(df)
                    total_read += rows_read

                    table = TABLE_MAP.get(fi.data_type)
                    if not table:
                        break

                    rows_written = self.db.upsert_dataframe(
                        df, table=table, batch_size=self.config.batch_size
                    )
                    total_written += rows_written
                    self.db.update_file_registry(fi, rows_read)
                    break

                except Exception as exc:
                    if attempt == self.config.max_retries:
                        total_failed += 1
                        failed_files.append(fi.file_path)
                    else:
                        time.sleep(self.config.retry_delay)

            # 进度
            elapsed = time.time() - start_time
            speed = idx / elapsed if elapsed > 0 else 0
            eta = (total_files - idx) / speed if speed > 0 else 0
            sys.stdout.write(
                f"\r  Progress: {idx}/{total_files} files "
                f"| Written: {_format_rows(total_written)} rows "
                f"| Elapsed: {elapsed:.0f}s | ETA: {eta:.0f}s"
            )
            sys.stdout.flush()

        elapsed = time.time() - start_time
        sys.stdout.write(
            f"\n  Done: {total_files} files | Read: {_format_rows(total_read)} "
            f"| Written: {_format_rows(total_written)} "
            f"| Failed: {_format_rows(total_failed)} "
            f"| Duration: {elapsed:.1f}s\n"
        )
        sys.stdout.flush()

        return SyncResult(
            rows_read=total_read, rows_written=total_written,
            rows_failed=total_failed, failed_files=failed_files,
        )

    def _read_file(self, fi: FileInfo) -> pd.DataFrame:
        if fi.suffix == "day":
            return self.reader.read_daily_by_file(fi.file_path)
        elif fi.suffix in ("lc5", "lc1"):
            return self.reader.read_lc_file(fi.file_path)
        return None

    def _read_file_append(self, fi: FileInfo) -> pd.DataFrame:
        table = TABLE_MAP.get(fi.data_type)
        if not table:
            return self._read_file(fi)

        max_date = self.db.get_max_trade_date(fi.symbol, table)
        if max_date is None:
            return self._read_file(fi)

        df = self._read_file(fi)
        if df is None or df.empty:
            return df

        df = df.reset_index()
        date_col = "date" if "date" in df.columns else "trade_date"
        if date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col])
            max_dt = pd.to_datetime(max_date)
            df = df[df[date_col] > max_dt]

        return df

    def _log_sync(self, mode: str, result: SyncResult, duration: float):
        self.db.insert_sync_log(
            sync_date=time.strftime("%Y-%m-%d"),
            mode=mode,
            rows_read=result.rows_read,
            rows_written=result.rows_written,
            rows_failed=result.rows_failed,
            duration_sec=round(duration, 2),
            status=result.status.value,
        )
        logger.info(
            "Sync [%s] done: read=%d, written=%d, failed=%d, duration=%.1fs",
            mode, result.rows_read, result.rows_written,
            result.rows_failed, duration
        )
