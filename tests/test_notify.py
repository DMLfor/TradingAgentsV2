"""notify 模块单元测试"""
from unittest.mock import MagicMock, patch

import pytest

from tdx_core.config import TdxConfig
from tdx_core.models import SyncResult
from tdx_core.notify import send_notification


class TestSendNotification:
    """send_notification 测试"""

    def test_no_config_skips(self, tdx_config):
        # 无通知配置时应跳过
        result = SyncResult(rows_read=10, rows_written=10)
        send_notification(result, 1.0, tdx_config)
        # 不抛异常即可

    def test_none_result(self, tdx_config):
        send_notification(None, 0.0, tdx_config)

    @patch("tdx_core.notify._send_dingtalk")
    def test_dingtalk_success(self, mock_ding, tdx_config):
        tdx_config.dingtalk_webhook = "https://example.com/webhook"
        result = SyncResult(rows_read=10, rows_written=10)
        send_notification(result, 1.0, tdx_config)
        mock_ding.assert_called_once()

    @patch("tdx_core.notify._send_email")
    @patch("tdx_core.notify._send_dingtalk", side_effect=Exception("fail"))
    def test_dingtalk_fail_fallback_email(self, mock_ding, mock_email, tdx_config):
        tdx_config.dingtalk_webhook = "https://example.com/webhook"
        tdx_config.smtp_host = "smtp.example.com"
        tdx_config.notify_email = "test@example.com"
        result = SyncResult(rows_read=10, rows_written=10)
        send_notification(result, 1.0, tdx_config)
        mock_email.assert_called_once()

    @patch("tdx_core.notify._send_email")
    def test_email_success(self, mock_email, tdx_config):
        tdx_config.smtp_host = "smtp.example.com"
        tdx_config.notify_email = "test@example.com"
        result = SyncResult(rows_read=10, rows_written=10)
        send_notification(result, 1.0, tdx_config)
        mock_email.assert_called_once()


class TestSendDingtalk:
    """_send_dingtalk 测试"""

    @patch("tdx_core.notify.requests.post")
    def test_send_dingtalk_success(self, mock_post):
        from tdx_core.notify import _send_dingtalk
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"errcode": 0}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        _send_dingtalk("https://example.com/webhook", "test msg")
        mock_post.assert_called_once()

    @patch("tdx_core.notify.requests.post")
    def test_send_dingtalk_api_error(self, mock_post):
        from tdx_core.notify import _send_dingtalk
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"errcode": 1, "errmsg": "error"}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        with pytest.raises(RuntimeError, match="DingTalk API error"):
            _send_dingtalk("https://example.com/webhook", "test msg")


class TestSendEmail:
    """_send_email 测试"""

    @patch("tdx_core.notify.smtplib.SMTP_SSL")
    def test_send_email_ssl(self, mock_smtp_cls):
        from tdx_core.notify import _send_email
        mock_server = MagicMock()
        mock_smtp_cls.return_value = mock_server

        config = TdxConfig(
            smtp_host="smtp.example.com",
            smtp_port=465,
            smtp_user="user@example.com",
            smtp_password="pass",
            notify_email="to@example.com",
        )
        _send_email(config, "test msg")
        mock_smtp_cls.assert_called_once()
        mock_server.login.assert_called_once()
        mock_server.sendmail.assert_called_once()
        mock_server.quit.assert_called_once()

    @patch("tdx_core.notify.smtplib.SMTP")
    def test_send_email_non_ssl(self, mock_smtp_cls):
        from tdx_core.notify import _send_email
        mock_server = MagicMock()
        mock_smtp_cls.return_value = mock_server

        config = TdxConfig(
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_user="user@example.com",
            smtp_password="pass",
            notify_email="to@example.com",
        )
        _send_email(config, "test msg")
        mock_smtp_cls.assert_called_once()
