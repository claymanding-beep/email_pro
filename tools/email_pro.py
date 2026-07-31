import logging
import smtplib
from collections.abc import Generator
from datetime import datetime
from email.mime.text import MIMEText
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

logger = logging.getLogger(__name__)


class EmailProTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        logger.info("========== [Send Email] Tool invoked ==========")
        # Get credentials configured in the provider
        credentials = self.runtime.credentials or {}
        smtp_host = credentials.get("smtp_host", "")
        smtp_port = int(credentials.get("smtp_port", 587))
        smtp_user = credentials.get("email_account", "")
        smtp_password = credentials.get("email_password", "")
        encrypt_method = credentials.get("encrypt_method", "TLS")
        logger.info(f"SMTP: {smtp_host}:{smtp_port}, user: {smtp_user}, encryption: {encrypt_method}")

        # Get tool parameters
        to_email = tool_parameters.get("to_email", "")
        subject = tool_parameters.get("subject", "")
        body = tool_parameters.get("body", "")
        logger.info(f"To: {to_email}, Subject: {subject}")

        if not to_email or not subject or not body:
            logger.warning("Missing required parameters")
            yield self.create_json_message({
                "status": "error",
                "error_type": "invalid_address",
                "message": "to_email, subject and body are required.",
                "to": to_email,
                "subject": subject
            })
            return

        try:
            # Build email message
            msg = MIMEText(body, "plain", "utf-8")
            msg["From"] = smtp_user
            msg["To"] = to_email
            msg["Subject"] = subject

            # Connect to SMTP server and send
            logger.info(f"Connecting to SMTP server ({encrypt_method})...")
            if encrypt_method == "SSL":
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30)
            else:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
                if encrypt_method == "TLS":
                    server.starttls()

            logger.info("Logging in...")
            server.login(smtp_user, smtp_password)
            logger.info("Sending email...")
            server.sendmail(smtp_user, [to_email], msg.as_string())
            server.quit()
            logger.info(f"Email sent successfully to {to_email}")

            yield self.create_json_message({
                "status": "success",
                "message": "Email sent successfully",
                "from": smtp_user,
                "to": to_email,
                "subject": subject,
                "timestamp": datetime.now().isoformat(timespec="seconds")
            })
        except smtplib.SMTPConnectError as e:
            logger.error(f"SMTP connection failed: {e}")
            yield self.create_json_message({
                "status": "error",
                "error_type": "connection_timeout",
                "message": f"Failed to connect to SMTP server: {e}",
                "to": to_email,
                "subject": subject
            })
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP authentication failed: {e}")
            yield self.create_json_message({
                "status": "error",
                "error_type": "auth_failed",
                "message": f"SMTP authentication failed: {e}",
                "to": to_email,
                "subject": subject
            })
        except smtplib.SMTPRecipientsRefused as e:
            logger.error(f"Recipient refused: {e}")
            yield self.create_json_message({
                "status": "error",
                "error_type": "invalid_address",
                "message": f"Recipient refused: {e}",
                "to": to_email,
                "subject": subject
            })
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            yield self.create_json_message({
                "status": "error",
                "error_type": "unknown",
                "message": str(e),
                "to": to_email,
                "subject": subject
            })
