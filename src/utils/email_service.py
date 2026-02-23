# src/utils/email_service.py
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dataclasses import dataclass
from typing import Optional
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class EmailConfig:
    """SMTP email configuration."""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""  # Use App Password for Gmail
    alert_email_from: str = ""
    alert_email_to: str = ""

    def is_configured(self) -> bool:
        """Check if email is properly configured."""
        return all([
            self.smtp_host,
            self.smtp_user,
            self.smtp_password,
            self.alert_email_from,
            self.alert_email_to
        ])


class EmailService:
    """Service for sending email alerts."""

    def __init__(self, config: EmailConfig):
        self.config = config

    def send_alert(
        self,
        subject: str,
        body: str,
        html_body: Optional[str] = None
    ) -> bool:
        """
        Send an email alert.

        Args:
            subject: Email subject line
            body: Plain text body
            html_body: Optional HTML body for rich formatting

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.config.is_configured():
            logger.warning("Email not configured, skipping alert")
            return False

        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.config.alert_email_from
            msg["To"] = self.config.alert_email_to

            # Attach plain text version
            msg.attach(MIMEText(body, "plain"))

            # Attach HTML version if provided
            if html_body:
                msg.attach(MIMEText(html_body, "html"))

            # Connect and send
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
                server.starttls()  # Enable TLS encryption
                server.login(self.config.smtp_user, self.config.smtp_password)
                server.sendmail(
                    self.config.alert_email_from,
                    self.config.alert_email_to,
                    msg.as_string()
                )

            logger.info(f"Alert email sent: {subject}")
            return True

        except smtplib.SMTPAuthenticationError:
            logger.error("SMTP authentication failed - check username/password")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    def send_pipeline_success(self, paper_count: int, duration_seconds: float):
        """Send notification for successful pipeline completion."""
        subject = "ResearchLineage Pipeline Completed"
        body = f"""
Pipeline completed successfully!

Papers processed: {paper_count}
Duration: {duration_seconds:.2f} seconds

Check the database for updated citation lineages.
"""
        return self.send_alert(subject, body)

    def send_pipeline_error(self, error_message: str, stage: str):
        """Send notification for pipeline failure."""
        subject = "ResearchLineage Pipeline Error"
        body = f"""
Pipeline encountered an error!

Stage: {stage}
Error: {error_message}

Please check the logs for more details.
"""
        return self.send_alert(subject, body)
