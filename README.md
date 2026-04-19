# TradingAgentsV2 — 通信达行情数据包

从通达信本地数据文件同步到 MySQL/SQLite，并提供 Python 查询 API，供交易策略和分析脚本直接调用。

## 项目结构

```
TradingAgentsV2/
├── tdx_core/            # 核心 Python 包
│   ├── __init__.py      # 公共 API 导出
│   ├── config.py        # TdxConfig 配置类
│   ├── db.py            # TdxDatabase 底层操作（读/写）
│   ├── models.py        # 数据模型与枚举
│   ├── query.py         # TdxQuery 高层查询 API
│   ├── reader.py        # 通达信二进制文件读取器
│   ├── scanner.py       # 文件扫描器
│   ├── sync.py          # 数据同步逻辑
│   └── notify.py        # 通知模块
├── config/
│   └── tdx_config.yaml  # 默认配置文件
├── sql/
│   ├── schema.sql       # SQLite DDL
│   ├── schema_mysql.sql # MySQL DDL
│   └── indexes.sql      # 索引
├── scripts/             # 运维脚本
├── tests/               # 测试
├── examples/            # 使用示例
└── pyproject.toml       # 包安装配置
```

## 快速开始

### 1. 安装

在项目根目录执行：

```bash
pip install -e .
```

这会将 `tdx_core` 以开发模式安装，之后在任何目录都能直接 `import`。

### 2. 配置数据库

编辑 `config/tdx_config.yaml`：

```yaml
db_type: "mysql"
mysql_host: "127.0.0.1"
mysql_port: 3306
mysql_user: "root"
mysql_password: "your_password"
mysql_database: "tdx_data"
```

### 3. 查询数据

```python
from tdx_core import TdxQuery

with TdxQuery() as q:
    # 日线
    df = q.get_daily("000001")
    df = q.get_daily("000001", start_date="2024-01-01", end_date="2024-12-31")

    # 5分钟线
    df5 = q.get_minute_5("000001", trade_date="2024-01-02")

    # 1分钟线
    df1 = q.get_minute_1("000001", trade_date="2024-01-02")

    # 股票列表
    codes = q.get_stock_list()

    # 最新交易日期
    latest = q.get_max_date("000001")

    # 自定义 SQL
    df = q.execute("SELECT * FROM tdx_daily WHERE code = %s LIMIT 5", ("000001",))
```

## 在其它项目中使用

### 方法 A：pip install -e（推荐）

```bash
pip install -e C:\Users\dblank\code\TradingAgentsV2
```

之后在任意 Python 环境中：

```python
from tdx_core import TdxQuery

q = TdxQuery()  # 自动加载默认配置
df = q.get_daily("000001")
```

### 方法 B：sys.path

```python
import sys
sys.path.insert(0, r"C:\Users\dblank\code\TradingAgentsV2")
from tdx_core import TdxQuery
```

### 方法 C：PYTHONPATH 环境变量

```bash
# Windows
set PYTHONPATH=C:\Users\dblank\code\TradingAgentsV2

# Linux/Mac
export PYTHONPATH=/path/to/TradingAgentsV2
```

## 自定义配置

```python
from tdx_core import TdxConfig, TdxQuery

# 手动构造
config = TdxConfig(
    mysql_host="10.0.0.1",
    mysql_password="prod_pwd",
    mysql_database="tdx_data",
)
q = TdxQuery(config=config)

# 或从 YAML 加载
q = TdxQuery(yaml_path="path/to/my_config.yaml")
```

## API 参考

### TdxQuery

| 方法 | 说明 |
|------|------|
| `get_daily(code, start_date, end_date)` | 查询日线 |
| `get_minute_5(code, trade_date)` | 查询5分钟线 |
| `get_minute_1(code, trade_date)` | 查询1分钟线 |
| `get_stock_list(table)` | 获取有数据的股票代码列表 |
| `get_trade_dates(code, table)` | 获取某股票全部交易日期 |
| `get_max_date(code, table)` | 获取最新交易日期 |
| `get_record_count(table, code)` | 获取记录条数 |
| `execute(sql, params)` | 执行自定义 SQL，返回 DataFrame |

### TdxDatabase

底层操作类，支持 MySQL/SQLite 双模式写入和查询。通常不需要直接使用。

### TdxConfig

配置类，字段参见 `config/tdx_config.yaml`。

## 数据同步

将通达信本地数据导入 MySQL：

```bash
# 初始化表结构
python scripts/tdx_init_db.py

# 全量导入
python scripts/tdx_full_import.py

# 增量同步
python scripts/tdx_sync.py
```

## 示例

```bash
python -m examples.01_basic_query       # 基本查询
python -m examples.02_custom_config     # 自定义配置
python -m examples.03_as_external_package  # 外部包调用
python -m examples.04_custom_sql        # 自定义 SQL
```

## 数据库表结构

| 表名 | 说明 | 主键 |
|------|------|------|
| `tdx_daily` | 日线行情 | (code, trade_date) |
| `tdx_minute_5` | 5分钟线 | (code, trade_date) |
| `tdx_minute_1` | 1分钟线 | (code, trade_date) |
| `tdx_file_registry` | 文件注册表（增量同步依据） | file_path |
| `tdx_sync_log` | 同步日志 | id |
