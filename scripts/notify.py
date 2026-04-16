"""Notification script for CI/CD pipeline events.

Supports Slack webhooks and email (via existing SMTP config).

Usage:
    python scripts/notify.py --channel slack --event training_complete --status success
    python scripts/notify.py --channel email --event bias_detected --details "Domain accuracy disparity 0.23"
"""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def send_slack(event: str, status: str, details: str = "") -> None:
    """Send notification via Slack webhook."""
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not webhook_url:
        print("SLACK_WEBHOOK_URL not set — skipping Slack notification")
        return

    color = "#36a64f" if status == "success" else "#ff0000"
    emoji = ":white_check_mark:" if status == "success" else ":x:"

    payload = {
        "attachments": [
            {
                "color": color,
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"{emoji} *ResearchLineage — {event}*\nStatus: `{status}`",
                        },
                    },
                ],
            }
        ]
    }

    if details:
        payload["attachments"][0]["blocks"].append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"```{details}```"},
            }
        )

    req = Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(req) as resp:
            print(f"Slack notification sent: {resp.status}")
    except Exception as exc:
        print(f"Failed to send Slack notification: {exc}")


def send_email(event: str, status: str, details: str = "") -> None:
    """Send notification via email using existing SMTP config."""
    try:
        import os
        from src.utils.email_service import EmailConfig, EmailService

        config = EmailConfig(
            smtp_host=os.environ.get("SMTP_HOST", "smtp.gmail.com"),
            smtp_port=int(os.environ.get("SMTP_PORT", "587")),
            smtp_user=os.environ.get("SMTP_USER", ""),
            smtp_password=os.environ.get("SMTP_PASSWORD", ""),
            alert_email_from=os.environ.get("ALERT_EMAIL_FROM", ""),
            alert_email_to=os.environ.get("ALERT_EMAIL_TO", ""),
        )
        service = EmailService(config)
        subject = f"ResearchLineage — {event} ({status})"
        body = f"Event: {event}\nStatus: {status}\n\n{details}"
        if service.send_alert(subject=subject, body=body):
            print("Email notification sent")
        else:
            print("Email not configured, skipping")
    except Exception as exc:
        print(f"Failed to send email: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Send pipeline notifications")
    parser.add_argument(
        "--channel",
        required=True,
        choices=["slack", "email", "both"],
        help="Notification channel",
    )
    parser.add_argument("--event", required=True, help="Event name (e.g., training_complete)")
    parser.add_argument("--status", default="success", choices=["success", "failure", "warning"])
    parser.add_argument("--details", default="", help="Additional details")
    args = parser.parse_args()

    if args.channel in ("slack", "both"):
        send_slack(args.event, args.status, args.details)
    if args.channel in ("email", "both"):
        send_email(args.event, args.status, args.details)


if __name__ == "__main__":
    from src.utils.logging import enable_script_logging
    enable_script_logging(__file__)
    main()
