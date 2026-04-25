"""示例2：自定义配置连接

适用于：MySQL 不在本机、或从其它项目目录调用

用法:
    cd tdx_data
    python -m examples.02_custom_config
"""
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tdx_core import TdxConfig, TdxQuery


def main():
    # 方式1: 手动构造 TdxConfig
    config = TdxConfig(
        db_type="mysql",
        mysql_host="127.0.0.1",
        mysql_port=3306,
        mysql_user="root",
        mysql_password="your_password",
        mysql_database="tdx_data",
    )
    q = TdxQuery(config=config)
    df = q.get_daily("000001")
    print(f"手动配置: {len(df)} 条日线记录")
    q.close()

    # 方式2: 从 YAML 文件加载
    q2 = TdxQuery(yaml_path=str(Path(ROOT) / "config" / "tdx_config.yaml"))
    df2 = q2.get_daily("600000")
    print(f"YAML 配置: 600000 共 {len(df2)} 条日线记录")
    q2.close()

    # 方式3: 使用环境变量覆盖（推荐生产环境）
    # export TDX_MYSQL_HOST=10.0.0.1
    # export TDX_MYSQL_PASSWORD=prod_password
    # config = TdxConfig(
    #     mysql_host=os.environ.get("TDX_MYSQL_HOST", "127.0.0.1"),
    #     mysql_password=os.environ.get("TDX_MYSQL_PASSWORD", ""),
    # )


if __name__ == "__main__":
    main()
