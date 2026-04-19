"""config 模块单元测试"""
import tempfile
from pathlib import Path

import pytest
import yaml

from tdx_data.config import TdxConfig


class TestTdxConfig:
    """TdxConfig 配置类测试"""

    def test_default_values(self):
        config = TdxConfig()
        assert config.tdx_dir == r"C:\new_tdx_mock"
        assert config.batch_size == 5000
        assert config.max_retries == 3
        assert config.log_retention_days == 30

    def test_vipdoc_dir(self, tmp_path):
        config = TdxConfig(tdx_dir=str(tmp_path))
        assert config.vipdoc_dir == tmp_path / "vipdoc"

    def test_supported_suffixes(self):
        config = TdxConfig()
        suffixes = config.supported_suffixes
        assert "day" in suffixes
        assert "lc5" in suffixes
        assert "lc1" in suffixes

    def test_data_type_map(self):
        config = TdxConfig()
        assert "lday" in config.DATA_TYPE_MAP
        assert "fzline" in config.DATA_TYPE_MAP
        assert "minline" in config.DATA_TYPE_MAP

    def test_from_yaml(self, tmp_path):
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text(yaml.dump({
            "tdx_dir": "/custom/path",
            "batch_size": 1000,
            "max_retries": 5,
        }), encoding="utf-8")

        config = TdxConfig.from_yaml(str(yaml_path))
        assert config.tdx_dir == "/custom/path"
        assert config.batch_size == 1000
        assert config.max_retries == 5

    def test_from_yaml_empty(self, tmp_path):
        yaml_path = tmp_path / "empty.yaml"
        yaml_path.write_text("", encoding="utf-8")
        config = TdxConfig.from_yaml(str(yaml_path))
        assert config.batch_size == 5000  # default
