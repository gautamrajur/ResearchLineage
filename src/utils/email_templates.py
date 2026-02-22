"""Email templates and sending for ResearchLineage alerts.

Use EmailTemplate for body content, then send with send_alert_email() when
SMTP/alert_email_to are configured. Reusable for PDF failures, pipeline success,
rate-limit warnings, etc.
"""
from dataclasses import dataclass
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from typing import Any, Dict, List, Optional

import logging
import smtplib

from src.utils.config import settings

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """Alert severity levels with corresponding colors."""

    INFO = ("#0969da", "ℹ️", "#ddf4ff")
    WARNING = ("#9a6700", "⚠️", "#fff8c5")
    ERROR = ("#cf222e", "❌", "#ffebe9")
    SUCCESS = ("#1a7f37", "✅", "#dafbe1")


@dataclass
class EmailTemplate:
    """
    Generic email template for ResearchLineage alerts.
    Pass details=rows from DB and optional columns for tabular emails.
    """

    title: str
    summary: str
    alert_level: AlertLevel = AlertLevel.INFO
    details: Optional[List[Dict[str, Any]]] = None
    columns: Optional[List[str]] = None
    footer_note: Optional[str] = None

    def __post_init__(self) -> None:
        if self.details is None:
            self.details = []

    def _get_columns(self) -> List[str]:
        if self.columns:
            return self.columns
        if self.details:
            return list(self.details[0].keys())
        return []

    def _format_column_header(self, col: str) -> str:
        return col.replace("_", " ").title()

    def _format_cell_value(self, value: Any, max_length: int = 60) -> str:
        if value is None:
            return "—"
        str_val = str(value)
        if len(str_val) > max_length:
            return str_val[: max_length - 3] + "..."
        return str_val

    def render_html(self) -> str:
        color, icon, bg_color = self.alert_level.value
        columns = self._get_columns()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

        table_rows = ""
        for i, row in enumerate(self.details or []):
            row_bg = "#f6f8fa" if i % 2 == 0 else "#ffffff"
            cells = "".join(
                f'<td style="padding: 10px 12px; border-bottom: 1px solid #e1e4e8; font-size: 13px;">'
                f"{self._format_cell_value(row.get(col))}</td>"
                for col in columns
            )
            table_rows += f'<tr style="background-color: {row_bg};">{cells}</tr>'

        table_headers = "".join(
            f'<th style="padding: 10px 12px; text-align: left; border-bottom: 2px solid #e1e4e8; '
            f'font-weight: 600; font-size: 12px; text-transform: uppercase; color: #57606a;">'
            f"{self._format_column_header(col)}</th>"
            for col in columns
        )

        footer_section = ""
        if self.footer_note:
            footer_section = f'''
            <div style="margin-top: 20px; padding: 12px; background-color: #f6f8fa;
                        border-radius: 6px; font-size: 13px; color: #57606a;">
                💡 {self.footer_note}
            </div>
            '''

        details_block = ""
        if self.details:
            details_block = f'''
            <div style="overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse; border: 1px solid #e1e4e8; border-radius: 6px;">
                    <thead>
                        <tr style="background-color: #f6f8fa;">
                            {table_headers}
                        </tr>
                    </thead>
                    <tbody>
                        {table_rows}
                    </tbody>
                </table>
            </div>
            '''

        return f'''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f6f8fa;">
    <div style="max-width: 700px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #24292f 0%, #32383f 100%); padding: 24px; border-radius: 8px 8px 0 0;">
            <h1 style="margin: 0; color: #ffffff; font-size: 20px; font-weight: 600;">📚 ResearchLineage Alert</h1>
        </div>
        <div style="background-color: #ffffff; padding: 24px; border: 1px solid #e1e4e8; border-top: none;">
            <div style="background-color: {bg_color}; border: 1px solid {color}; border-radius: 6px; padding: 16px; margin-bottom: 20px;">
                <div style="display: flex; align-items: center;">
                    <span style="font-size: 24px; margin-right: 12px;">{icon}</span>
                    <div>
                        <div style="font-weight: 600; color: {color}; font-size: 16px;">{self.title}</div>
                        <div style="color: #57606a; font-size: 14px; margin-top: 4px;">{self.summary}</div>
                    </div>
                </div>
            </div>
            {details_block}
            {footer_section}
        </div>
        <div style="background-color: #f6f8fa; padding: 16px 24px; border: 1px solid #e1e4e8; border-top: none; border-radius: 0 0 8px 8px;">
            <div style="font-size: 12px; color: #57606a; text-align: center;">Sent by ResearchLineage Pipeline · {timestamp}</div>
        </div>
    </div>
</body>
</html>
'''

    def render_plain(self) -> str:
        columns = self._get_columns()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        lines = [
            "=" * 60,
            "ResearchLineage Alert",
            "=" * 60,
            "",
            f"[{self.alert_level.name}] {self.title}",
            "",
            self.summary,
            "",
        ]
        if self.details:
            lines.append("-" * 60)
            for i, row in enumerate(self.details, 1):
                lines.append(f"\n#{i}")
                for col in columns:
                    value = self._format_cell_value(row.get(col))
                    lines.append(f"  {self._format_column_header(col)}: {value}")
            lines.append("")
        if self.footer_note:
            lines.extend(["-" * 60, f"Note: {self.footer_note}", ""])
        lines.extend(["-" * 60, f"Sent: {timestamp}"])
        return "\n".join(lines)


def send_alert_email(
    subject: str,
    template: EmailTemplate,
    from_addr: Optional[str] = None,
    to_addrs: Optional[str] = None,
) -> bool:
    """
    Send an alert email using the given subject and template.
    Uses settings.smtp_* and settings.alert_email_* when from_addr/to_addrs not provided.
    Returns True if sent, False if SMTP not configured or send failed.
    """
    if not (settings.smtp_host and (to_addrs or settings.alert_email_to)):
        return False
    to_addrs = to_addrs or settings.alert_email_to
    from_addr = (
        from_addr
        or settings.alert_email_from
        or settings.smtp_user
        or "noreply@researchlineage"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addrs
    msg.attach(MIMEText(template.render_plain(), "plain"))
    msg.attach(MIMEText(template.render_html(), "html"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            if settings.smtp_user and settings.smtp_password:
                server.login(settings.smtp_user, settings.smtp_password)
            to_list = [a.strip() for a in to_addrs.split(",") if a.strip()]
            server.sendmail(from_addr, to_list, msg.as_string())
        return True
    except Exception as e:
        logger.exception("Failed to send alert email: %s", e)
        return False
