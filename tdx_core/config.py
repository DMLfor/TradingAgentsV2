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
    mysql_password: str = ""
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

    # minishare API
    minishare_token: str = ""

    # Metadata files
    metadata_path: str = "config/stock_metadata.json"
    names_path: str = "config/stock_names.json"
    metadata_source: str = ""  # CSV source path (for generation tracking)

    # 目录映射：子目录名 → (数据类型, 文件后缀, 目标表, reader方法)
    DATA_TYPE_MAP: Dict = field(default_factory=lambda: {
        "lday":    ("daily",     "day", "tdx_daily",     "daily"),
        "fzline":  ("minute_5",  "lc5", "tdx_minute_5",  "fzline"),
        "minline": ("minute_1",  "lc1", "tdx_minute_1",  "minute"),
    })

    @staticmethod
    def _load_dotenv() -> None:
        """Load .env file into os.environ (if exists)."""
        env_path = Path(__file__).parent.parent / ".env"
        if not env_path.exists():
            return
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, val)

    def __post_init__(self):
        """Auto-detect cloud SQLite and switch db_type accordingly.

        If data/tdx_data_cloud.db or .db.gz exists (e.g. OpenClaw cloud env),
        override db_type to sqlite regardless of YAML config.
        Local env without these files continues to use MySQL.
        """
        # Load .env first so os.getenv can pick it up
        self._load_dotenv()

        cloud_db = Path(__file__).parent.parent / "data" / "tdx_data_cloud.db"
        cloud_db_gz = cloud_db.with_suffix(".db.gz")
        if cloud_db.exists() or cloud_db_gz.exists():
            self.db_type = "sqlite"
            self.db_path = str(cloud_db)
        # Allow env override for sensitive fields
        if os.getenv("MYSQL_PASSWORD"):
            self.mysql_password = os.getenv("MYSQL_PASSWORD")
        if os.getenv("TDX_DB_PATH"):
            self.db_path = os.getenv("TDX_DB_PATH")
        if os.getenv("MINISHARE_TOKEN"):
            self.minishare_token = os.getenv("MINISHARE_TOKEN")

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
