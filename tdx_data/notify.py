"""通知模块：钉钉机器人 / 邮件"""
import json
import logging
import smtplib
from email.mime.text import MIMEText
from typing import Optional

import requests

from .config import TdxConfig
from .models import SyncResult

logger = logging.getLogger(__name__)


def send_notification(result: Optional[SyncResult], duration: float,
                      config: TdxConfig):
    """发送同步结果通知

    优先钉钉机器人，失败回退邮件，均未配置则跳过。
    """
    if result is None:
        msg = "TDX Sync: 无变更，同步跳过"
    else:
        msg = (
            f"TDX Data Sync Report\n"
            f"  读取行数: {result.rows_read}\n"
            f"  写入行数: {result.rows_written}\n"
            f"  失败文件: {result.rows_failed}\n"
            f"  失败列表: {result.failed_files[:10]}\n"
            f"  耗时: {duration:.1f}s\n"
            f"  状态: {result.status.value}"
        )

    if config.dingtalk_webhook:
        try:
            _send_dingtalk(config.dingtalk_webhook, msg)
            return
        except Exception as exc:
            logger.warning("DingTalk notification failed: %s", exc)

    if config.smtp_host and config.notify_email:
        try:
            _send_email(config, msg)
            return
        except Exception as exc:
            logger.warning("Email notification failed: %s", exc)

    logger.info("No notification channel configured, skipped")


def _send_dingtalk(webhook: str, msg: str):
    """发送钉钉机器人消息"""
    payload = {
        "msgtype": "text",
        "text": {"content": msg},
    }
    resp = requests.post(
        webhook,
        data=json.dumps(payload),
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("errcode") != 0:
        raise RuntimeError(f"DingTalk API error: {data}")


def _send_email(config: TdxConfig, msg: str):
    """发送邮件通知"""
    mime = MIMEText(msg, "plain", "utf-8")
    mime["Subject"] = "TDX Data Sync Report"
    mime["From"] = config.smtp_user
    mime["To"] = config.notify_email

    if config.smtp_port == 465:
        server = smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=10)
    else:
        server = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=10)

    try:
        if config.smtp_user and config.smtp_password:
            server.login(config.smtp_user, config.smtp_password)
        server.sendmail(config.smtp_user, [config.notify_email], mime.as_string())
    finally:
        server.quit()
