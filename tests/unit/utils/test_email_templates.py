"""Unit tests for src.utils.email_templates."""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from src.utils.email_templates import (
    AlertLevel,
    EmailTemplate,
    send_alert_email,
)


# ═══════════════════════════════════════════════════════════════════════════
# AlertLevel
# ═══════════════════════════════════════════════════════════════════════════


class TestAlertLevel:

    def test_info(self):
        """INFO has blue color and info icon."""
        color, icon, bg = AlertLevel.INFO.value
        assert color == "#0969da"
        assert icon == "ℹ️"
        assert bg == "#ddf4ff"

    def test_warning(self):
        """WARNING has yellow/amber values."""
        color, icon, bg = AlertLevel.WARNING.value
        assert color == "#9a6700"
        assert icon == "⚠️"

    def test_error(self):
        """ERROR has red values."""
        color, icon, bg = AlertLevel.ERROR.value
        assert color == "#cf222e"
        assert icon == "❌"

    def test_success(self):
        """SUCCESS has green values."""
        color, icon, bg = AlertLevel.SUCCESS.value
        assert color == "#1a7f37"
        assert icon == "✅"

    def test_all_have_three_values(self):
        """All levels have (color, icon, bg) tuple."""
        for level in AlertLevel:
            color, icon, bg = level.value
            assert color.startswith("#")
            assert bg.startswith("#")


# ═══════════════════════════════════════════════════════════════════════════
# EmailTemplate Init
# ═══════════════════════════════════════════════════════════════════════════


class TestEmailTemplateInit:

    def test_minimal(self):
        """Creates with required args only."""
        t = EmailTemplate(title="Test", summary="Summary")

        assert t.title == "Test"
        assert t.summary == "Summary"
        assert t.alert_level == AlertLevel.INFO
        assert t.details == []

    def test_full(self):
        """Creates with all args."""
        details = [{"paper_id": "p1"}]
        t = EmailTemplate(
            title="Alert",
            summary="Sum",
            alert_level=AlertLevel.ERROR,
            details=details,
            columns=["paper_id"],
            footer_note="Note",
        )

        assert t.alert_level == AlertLevel.ERROR
        assert t.details == details
        assert t.footer_note == "Note"

    def test_none_details_becomes_empty(self):
        """None details becomes empty list."""
        t = EmailTemplate(title="T", summary="S", details=None)
        assert t.details == []


# ═══════════════════════════════════════════════════════════════════════════
# EmailTemplate._get_columns
# ═══════════════════════════════════════════════════════════════════════════


class TestGetColumns:

    def test_explicit(self):
        """Uses explicit columns."""
        t = EmailTemplate(
            title="T", summary="S",
            columns=["a", "b"],
            details=[{"a": 1, "x": 2}],
        )
        assert t._get_columns() == ["a", "b"]

    def test_inferred(self):
        """Infers from first detail row."""
        t = EmailTemplate(
            title="T", summary="S",
            details=[{"paper_id": "p1", "title": "T"}],
        )
        cols = t._get_columns()
        assert "paper_id" in cols
        assert "title" in cols

    def test_empty(self):
        """Returns empty when no details."""
        t = EmailTemplate(title="T", summary="S")
        assert t._get_columns() == []


# ═══════════════════════════════════════════════════════════════════════════
# EmailTemplate._format_column_header
# ═══════════════════════════════════════════════════════════════════════════


class TestFormatColumnHeader:

    def test_snake_case(self):
        """Converts snake_case to Title Case."""
        t = EmailTemplate(title="T", summary="S")
        assert t._format_column_header("paper_id") == "Paper Id"
        assert t._format_column_header("fail_runs") == "Fail Runs"

    def test_single_word(self):
        """Single word gets title case."""
        t = EmailTemplate(title="T", summary="S")
        assert t._format_column_header("simple") == "Simple"


# ═══════════════════════════════════════════════════════════════════════════
# EmailTemplate._format_cell_value
# ═══════════════════════════════════════════════════════════════════════════


class TestFormatCellValue:

    def test_none(self):
        """None becomes em-dash."""
        t = EmailTemplate(title="T", summary="S")
        assert t._format_cell_value(None) == "—"

    def test_truncate(self):
        """Long strings truncated."""
        t = EmailTemplate(title="T", summary="S")
        result = t._format_cell_value("A" * 100, max_length=60)
        assert len(result) == 60
        assert result.endswith("...")

    def test_preserve_short(self):
        """Short strings preserved."""
        t = EmailTemplate(title="T", summary="S")
        assert t._format_cell_value("short") == "short"

    def test_numbers(self):
        """Numbers converted to strings."""
        t = EmailTemplate(title="T", summary="S")
        assert t._format_cell_value(42) == "42"
        assert t._format_cell_value(3.14) == "3.14"


# ═══════════════════════════════════════════════════════════════════════════
# EmailTemplate.render_html
# ═══════════════════════════════════════════════════════════════════════════


class TestRenderHtml:

    def test_contains_title(self):
        """HTML contains title and summary."""
        t = EmailTemplate(title="Test Alert", summary="Test summary")
        html = t.render_html()
        assert "Test Alert" in html
        assert "Test summary" in html

    def test_alert_colors(self):
        """HTML contains alert level colors."""
        t = EmailTemplate(title="E", summary="S", alert_level=AlertLevel.ERROR)
        html = t.render_html()
        color, icon, bg = AlertLevel.ERROR.value
        assert color in html
        assert bg in html

    def test_table(self):
        """HTML renders table with details."""
        t = EmailTemplate(
            title="R", summary="S",
            details=[{"paper_id": "p1"}, {"paper_id": "p2"}],
        )
        html = t.render_html()
        assert "p1" in html
        assert "p2" in html
        assert "<table" in html

    def test_footer(self):
        """HTML includes footer note."""
        t = EmailTemplate(title="T", summary="S", footer_note="Check this")
        html = t.render_html()
        assert "Check this" in html

    def test_timestamp(self):
        """HTML includes timestamp."""
        t = EmailTemplate(title="T", summary="S")
        html = t.render_html()
        assert str(datetime.now().year) in html

    def test_valid_structure(self):
        """HTML has valid document structure."""
        t = EmailTemplate(title="T", summary="S")
        html = t.render_html()
        assert "<!DOCTYPE html>" in html
        assert "<html>" in html
        assert "</html>" in html


# ═══════════════════════════════════════════════════════════════════════════
# EmailTemplate.render_plain
# ═══════════════════════════════════════════════════════════════════════════


class TestRenderPlain:

    def test_contains_title(self):
        """Plain text contains title and summary."""
        t = EmailTemplate(title="Test Alert", summary="Summary")
        text = t.render_plain()
        assert "Test Alert" in text
        assert "Summary" in text

    def test_alert_level(self):
        """Plain text contains alert level name."""
        t = EmailTemplate(title="E", summary="S", alert_level=AlertLevel.ERROR)
        text = t.render_plain()
        assert "[ERROR]" in text

    def test_details_numbered(self):
        """Details are numbered."""
        t = EmailTemplate(
            title="R", summary="S",
            details=[{"id": "1"}, {"id": "2"}],
        )
        text = t.render_plain()
        assert "#1" in text
        assert "#2" in text

    def test_footer(self):
        """Plain text includes footer."""
        t = EmailTemplate(title="T", summary="S", footer_note="Note here")
        text = t.render_plain()
        assert "Note here" in text


# ═══════════════════════════════════════════════════════════════════════════
# send_alert_email
# ═══════════════════════════════════════════════════════════════════════════


class TestSendAlertEmail:

    def test_no_smtp_host(self):
        """Returns False when SMTP host not set."""
        with patch("src.utils.email_templates.settings") as s:
            s.smtp_host = None
            s.alert_email_to = None

            t = EmailTemplate(title="T", summary="S")
            assert send_alert_email("Subject", t) is False

    def test_no_recipient(self):
        """Returns False when no recipient."""
        with patch("src.utils.email_templates.settings") as s:
            s.smtp_host = "smtp.example.com"
            s.alert_email_to = ""

            t = EmailTemplate(title="T", summary="S")
            assert send_alert_email("Subject", t) is False

    def test_success(self):
        """Returns True on successful send."""
        with patch("src.utils.email_templates.settings") as s:
            s.smtp_host = "smtp.gmail.com"
            s.smtp_port = 587
            s.smtp_user = "user@gmail.com"
            s.smtp_password = "pass"
            s.alert_email_to = "admin@example.com"
            s.alert_email_from = "sender@example.com"

            with patch("src.utils.email_templates.smtplib.SMTP") as mock_smtp:
                server = MagicMock()
                mock_smtp.return_value.__enter__.return_value = server

                t = EmailTemplate(title="Alert", summary="Test")
                assert send_alert_email("Subject", t) is True

                server.starttls.assert_called_once()
                server.login.assert_called_once()
                server.sendmail.assert_called_once()

    def test_smtp_error(self):
        """Returns False on SMTP error."""
        with patch("src.utils.email_templates.settings") as s:
            s.smtp_host = "smtp.example.com"
            s.smtp_port = 587
            s.smtp_user = "user"
            s.smtp_password = "pass"
            s.alert_email_to = "admin@example.com"
            s.alert_email_from = "alerts@example.com"

            with patch("src.utils.email_templates.smtplib.SMTP") as mock_smtp:
                mock_smtp.return_value.__enter__.side_effect = Exception("Refused")

                t = EmailTemplate(title="T", summary="S")
                assert send_alert_email("Subject", t) is False

    def test_multiple_recipients(self):
        """Handles comma-separated recipients."""
        with patch("src.utils.email_templates.settings") as s:
            s.smtp_host = "smtp.example.com"
            s.smtp_port = 587
            s.smtp_user = "user"
            s.smtp_password = "pass"
            s.alert_email_to = "a@x.com, b@x.com, c@x.com"
            s.alert_email_from = "sender@x.com"

            with patch("src.utils.email_templates.smtplib.SMTP") as mock_smtp:
                server = MagicMock()
                mock_smtp.return_value.__enter__.return_value = server

                t = EmailTemplate(title="T", summary="S")
                send_alert_email("Subject", t)

                to_list = server.sendmail.call_args[0][1]
                assert len(to_list) == 3

    def test_override_addrs(self):
        """Uses provided from/to over settings."""
        with patch("src.utils.email_templates.settings") as s:
            s.smtp_host = "smtp.example.com"
            s.smtp_port = 587
            s.smtp_user = "user"
            s.smtp_password = "pass"
            s.alert_email_to = "default@example.com"
            s.alert_email_from = "default-sender@example.com"

            with patch("src.utils.email_templates.smtplib.SMTP") as mock_smtp:
                server = MagicMock()
                mock_smtp.return_value.__enter__.return_value = server

                t = EmailTemplate(title="T", summary="S")
                send_alert_email("Subject", t, from_addr="custom@s.com", to_addrs="custom@r.com")

                args = server.sendmail.call_args[0]
                assert args[0] == "custom@s.com"
                assert "custom@r.com" in args[1]

    def test_skip_login_no_creds(self):
        """Skips login when no credentials."""
        with patch("src.utils.email_templates.settings") as s:
            s.smtp_host = "smtp.example.com"
            s.smtp_port = 587
            s.smtp_user = None
            s.smtp_password = None
            s.alert_email_to = "admin@example.com"
            s.alert_email_from = "sender@example.com"

            with patch("src.utils.email_templates.smtplib.SMTP") as mock_smtp:
                server = MagicMock()
                mock_smtp.return_value.__enter__.return_value = server

                t = EmailTemplate(title="T", summary="S")
                send_alert_email("Subject", t)

                server.login.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════════════════


class TestEdgeCases:

    def test_unicode(self):
        """Handles Unicode in all fields."""
        t = EmailTemplate(
            title="日本語タイトル 🔬",
            summary="Résumé",
            details=[{"论文": "中文"}],
            footer_note="¡Importante!",
        )
        html = t.render_html()
        assert "日本語" in html
        assert "Résumé" in html

    def test_empty_details(self):
        """Handles empty detail values."""
        t = EmailTemplate(
            title="T", summary="S",
            details=[{"paper_id": "", "title": ""}],
        )
        html = t.render_html()
        assert "<table" in html

    def test_large_table(self):
        """Handles 100 detail rows."""
        details = [{"id": f"p{i}"} for i in range(100)]
        t = EmailTemplate(title="T", summary="S", details=details)

        html = t.render_html()
        assert "p0" in html
        assert "p99" in html

    def test_mixed_types(self):
        """Handles mixed types in details."""
        t = EmailTemplate(
            title="T", summary="S",
            details=[{
                "str": "text",
                "int": 42,
                "float": 3.14,
                "bool": True,
                "none": None,
            }],
        )
        html = t.render_html()
        assert "42" in html
        assert "—" in html  # None -> em-dash
