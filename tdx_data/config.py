"""通信达数据同步全局配置"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict


@dataclass
class TdxConfig:
    tdx_dir: str = r"C:\new_tdx_mock"

    # 数据库配置
    db_type: str = "mysql"  # "sqlite" 或 "mysql"
    db_path: str = "tdx_data.db"  # SQLite 文件路径

    # MySQL 连接参数
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = "tdx123456"
    mysql_database: str = "tdx_data"

    batch_size: int = 5000
    data_types: tuple = ("daily",)  # 只导入日线，需要分钟线改为 ("daily", "minute_5", "minute_1")
    markets: tuple = ("sh", "sz")   # 只导入沪深，需要全市场改为 ("sh", "sz", "bj", "ds")
    max_retries: int = 3
    retry_delay: float = 1.0
    log_dir: str = "logs"
    log_retention_days: int = 30

    # 通知配置
    dingtalk_webhook: str = ""
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    notify_email: str = ""

    # 目录映射：子目录名 → (数据类型, 文件后缀, 目标表, reader方法)
    DATA_TYPE_MAP: Dict = field(default_factory=lambda: {
        "lday":    ("daily",     "day", "tdx_daily",     "daily"),
        "fzline":  ("minute_5",  "lc5", "tdx_minute_5",  "fzline"),
        "minline": ("minute_1",  "lc1", "tdx_minute_1",  "minute"),
    })

    @property
    def vipdoc_dir(self) -> Path:
        return Path(self.tdx_dir) / "vipdoc"

    @property
    def supported_suffixes(self) -> set:
        return {v[1] for v in self.DATA_TYPE_MAP.values()}

    @property
    def mysql_dsn(self) -> str:
        return f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"

    @classmethod
    def from_yaml(cls, path: str) -> "TdxConfig":
        """从 YAML 文件加载配置"""
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
