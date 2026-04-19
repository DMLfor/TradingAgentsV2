"""目录扫描与变更检测"""
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from .config import TdxConfig
from .models import FileInfo

logger = logging.getLogger(__name__)


class TdxScanner:
    """通信达数据目录扫描器

    递归扫描 vipdoc 下所有子目录，识别 .day/.lc5/.lc1 文件，
    提取 market/symbol/data_type 等元信息，支持变更检测。
    """

    def __init__(self, config: TdxConfig = None):
        self.config = config or TdxConfig()

    def scan_all(self) -> List[FileInfo]:
        """递归扫描 vipdoc 下所有数据文件

        Returns:
            FileInfo 列表
        """
        vipdoc = self.config.vipdoc_dir
        if not vipdoc.exists():
            logger.error("vipdoc directory not found: %s", vipdoc)
            return []

        results = []
        for market_dir in sorted(vipdoc.iterdir()):
            if not market_dir.is_dir():
                continue
            market = market_dir.name
            if market not in self.config.markets:
                continue
            for subdir in sorted(market_dir.iterdir()):
                if not subdir.is_dir():
                    continue
                subdir_name = subdir.name
                if subdir_name not in self.config.DATA_TYPE_MAP:
                    continue
                data_type, suffix, _, _ = self.config.DATA_TYPE_MAP[subdir_name]
                if data_type not in self.config.data_types:
                    continue
                for f in sorted(subdir.glob(f"*.{suffix}")):
                    results.append(self._file_to_info(f, market, data_type, suffix))

        logger.info("Scan complete: %d files found", len(results))
        return results

    def scan_market(self, market: str, data_type: str = None) -> List[FileInfo]:
        """扫描指定市场的文件

        Args:
            market: sh/sz/bj/ds
            data_type: daily/minute_5/minute_1，None 表示所有类型
        """
        vipdoc = self.config.vipdoc_dir / market
        if not vipdoc.exists():
            return []

        results = []
        for subdir in sorted(vipdoc.iterdir()):
            if not subdir.is_dir():
                continue
            subdir_name = subdir.name
            if subdir_name not in self.config.DATA_TYPE_MAP:
                continue
            dt, suffix, _, _ = self.config.DATA_TYPE_MAP[subdir_name]
            if dt not in self.config.data_types:
                continue
            if data_type and dt != data_type:
                continue
            for f in sorted(subdir.glob(f"*.{suffix}")):
                results.append(self._file_to_info(f, market, dt, suffix))

        return results

    def detect_changes(self, known: Dict[str, FileInfo],
                       current: List[FileInfo]) -> Dict[str, List[FileInfo]]:
        """对比已知文件与当前文件，返回变更集

        Args:
            known: {file_path: FileInfo} from db
            current: [FileInfo] from scan
        Returns:
            {"new": [...], "modified": [...], "unchanged": [...]}
        """
        new_files, modified, unchanged = [], [], []

        for fi in current:
            if fi.file_path not in known:
                new_files.append(fi)
            elif (fi.file_mtime != known[fi.file_path].file_mtime
                  or fi.file_size != known[fi.file_path].file_size):
                modified.append(fi)
            else:
                unchanged.append(fi)

        logger.info(
            "Change detection: new=%d, modified=%d, unchanged=%d",
            len(new_files), len(modified), len(unchanged)
        )
        return {"new": new_files, "modified": modified, "unchanged": unchanged}

    @staticmethod
    def compute_md5(file_path: str) -> str:
        """计算文件 MD5"""
        h = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _file_to_info(self, f: Path, market: str,
                      data_type: str, suffix: str) -> FileInfo:
        stat = f.stat()
        return FileInfo(
            file_path=str(f),
            market=market,
            symbol=self._extract_symbol(f.name, market),
            data_type=data_type,
            suffix=suffix,
            file_size=stat.st_size,
            file_mtime=datetime.fromtimestamp(stat.st_mtime).isoformat(),
        )

    @staticmethod
    def _extract_symbol(filename: str, market: str) -> str:
        stem = Path(filename).stem
        if market in ("sh", "sz", "bj"):
            return stem[2:]
        return stem
