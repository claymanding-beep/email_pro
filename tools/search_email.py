import imaplib
import email
import logging
import re
from collections.abc import Generator
from datetime import datetime, timedelta
from email.header import decode_header
from html import unescape
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

logger = logging.getLogger(__name__)


def html_to_plain_text(html: str) -> str:
    """Convert HTML content to plain text by stripping tags."""
    # Remove <style> and <script> blocks entirely
    text = re.sub(r'<(style|script)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
    # Replace <br>, <p>, <div>, <li>, <tr> with newlines
    text = re.sub(r'<(br|/p|/div|/li|/tr|/h[1-6])[^>]*>', '\n', text, flags=re.IGNORECASE)
    # Strip all remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Decode HTML entities (e.g. &nbsp; &amp; &lt;)
    text = unescape(text)
    # Collapse multiple blank lines into one
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def decode_header_value(value: str) -> str:
    """Decode an email header value (handles encoded words like =?UTF-8?B?...?=)"""
    if not value:
        return ""
    decoded = ""
    try:
        parts = decode_header(value)
        for part, charset in parts:
            if isinstance(part, bytes):
                decoded += part.decode(charset or "utf-8", errors="replace")
            else:
                decoded += part
    except Exception:
        decoded = value
    return decoded


def is_ascii_only(text: str) -> bool:
    """Check if a string contains only ASCII characters."""
    try:
        text.encode('ascii')
        return True
    except UnicodeEncodeError:
        return False


class SearchEmailTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        logger.info("========== [Search Email] Tool invoked ==========")
        # Get credentials configured in the provider
        credentials = self.runtime.credentials or {}
        smtp_host = credentials.get("smtp_host", "")
        smtp_user = credentials.get("email_account", "")
        smtp_password = credentials.get("email_password", "")

        # Derive IMAP host from SMTP host (common convention)
        imap_host = smtp_host.replace("smtp.", "imap.")
        imap_port = 993  # Standard IMAP SSL port
        logger.info(f"IMAP host: {imap_host}:{imap_port}, user: {smtp_user}")

        # Get tool parameters
        folder = tool_parameters.get("folder", "INBOX")
        sender = tool_parameters.get("sender", "").strip()
        subject = tool_parameters.get("subject", "").strip()
        days = int(tool_parameters.get("days", 0))
        max_results = int(tool_parameters.get("max_results", 10))
        logger.info(f"Folder: {folder}, Sender: '{sender}', Subject: '{subject}', Days: {days}, Max: {max_results}")

        mail = None
        try:
            # Connect to IMAP server with timeout
            logger.info("Connecting to IMAP server...")
            mail = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=30)
            mail.login(smtp_user, smtp_password)
            logger.info("Logged in, selecting folder...")
            mail.select(folder)

            # Build IMAP search criteria (only ASCII-safe parts)
            # Non-ASCII subject (e.g. Chinese) will be filtered client-side
            criteria = []
            subject_needs_client_filter = False

            if sender:
                criteria.append(f'FROM "{sender}"')
            if subject:
                if is_ascii_only(subject):
                    criteria.append(f'SUBJECT "{subject}"')
                else:
                    # Non-ASCII subject: skip IMAP search, filter locally
                    subject_needs_client_filter = True
                    logger.info(f"Subject contains non-ASCII chars, will filter client-side: '{subject}'")
            if days > 0:
                since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
                criteria.append(f'SINCE {since_date}')
                logger.info(f"Date filter: emails since {since_date}")

            use_imap_search = bool(criteria)

            if use_imap_search:
                search_query = " ".join(criteria)
                logger.info(f"IMAP search query: {search_query}")

                status, messages = mail.search(None, search_query)
                email_ids = messages[0].split() if messages[0] else []
                logger.info(f"IMAP server returned {len(email_ids)} results")

                # If non-ASCII subject needs client-side filtering, or
                # IMAP search returned very few results, fetch and filter locally
                if subject_needs_client_filter or (len(email_ids) < 3 and not days):
                    logger.info("Applying client-side filtering...")
                    # Use IMAP results as candidates (already filtered by sender/date),
                    # only fall back to ALL if no IMAP results and no other criteria
                    if email_ids:
                        candidates = email_ids
                    else:
                        status, all_messages = mail.search(None, 'ALL')
                        candidates = all_messages[0].split() if all_messages[0] else []
                    logger.info(f"Scanning {len(candidates)} emails locally")

                    matched_ids = []
                    for eid in reversed(candidates):
                        if len(matched_ids) >= max_results:
                            break
                        status, msg_data = mail.fetch(eid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                        if status != "OK":
                            continue
                        header_data = msg_data[0][1]
                        msg = email.message_from_bytes(header_data)
                        from_value = decode_header_value(msg.get("From", ""))
                        subject_value = decode_header_value(msg.get("Subject", ""))

                        match = True
                        if sender and sender.lower() not in from_value.lower():
                            match = False
                        if subject_needs_client_filter and subject.lower() not in subject_value.lower():
                            match = False

                        if match:
                            matched_ids.append(eid)
                            logger.info(f"  Client-side match: {subject_value} (from: {from_value})")

                    email_ids = matched_ids
                else:
                    # Limit to max_results (most recent)
                    email_ids = list(email_ids[-max_results:])
            else:
                # No IMAP filters, get the most recent emails and filter locally if needed
                status, messages = mail.search(None, 'ALL')
                all_ids = messages[0].split() if messages[0] else []
                logger.info(f"Total emails: {len(all_ids)}")

                if subject_needs_client_filter:
                    logger.info("Applying client-side subject filter on all emails...")
                    matched_ids = []
                    # Only scan the most recent emails to avoid hanging on large mailboxes
                    scan_limit = min(len(all_ids), max(max_results * 50, 500))
                    scan_ids = all_ids[-scan_limit:]
                    logger.info(f"Scanning last {len(scan_ids)} emails (limit: {scan_limit})")
                    for eid in reversed(scan_ids):
                        if len(matched_ids) >= max_results:
                            break
                        status, msg_data = mail.fetch(eid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                        if status != "OK":
                            continue
                        header_data = msg_data[0][1]
                        msg = email.message_from_bytes(header_data)
                        subject_value = decode_header_value(msg.get("Subject", ""))
                        if subject.lower() in subject_value.lower():
                            matched_ids.append(eid)
                            logger.info(f"  Client-side match: {subject_value}")
                    email_ids = matched_ids
                else:
                    email_ids = list(all_ids[-max_results:])

            # Fetch full email content for results
            results = []
            for eid in reversed(email_ids):
                if isinstance(eid, int):
                    eid_bytes = str(eid).encode()
                else:
                    eid_bytes = eid

                status, msg_data = mail.fetch(eid_bytes if isinstance(eid_bytes, bytes) else eid, "(RFC822)")
                if status != "OK":
                    continue

                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                subject_decoded = decode_header_value(msg.get("Subject", ""))
                from_decoded = decode_header_value(msg.get("From", ""))

                # Get email body (prefer plain text, fall back to HTML)
                body = ""
                html_body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        content_disp = str(part.get("Content-Disposition", ""))
                        # Skip attachments
                        if "attachment" in content_disp:
                            continue
                        payload = part.get_payload(decode=True)
                        if not payload:
                            continue
                        charset = part.get_content_charset() or "utf-8"
                        try:
                            text = payload.decode(charset, errors="replace")
                        except Exception:
                            continue
                        if content_type == "text/plain" and not body:
                            body = text
                        elif content_type == "text/html" and not html_body:
                            html_body = text
                else:
                    content_type = msg.get_content_type()
                    payload = msg.get_payload(decode=True)
                    if payload:
                        charset = msg.get_content_charset() or "utf-8"
                        try:
                            text = payload.decode(charset, errors="replace")
                        except Exception:
                            text = ""
                        if content_type == "text/plain":
                            body = text
                        elif content_type == "text/html":
                            html_body = text

                # If no plain text body, convert HTML to plain text
                if not body and html_body:
                    body = html_to_plain_text(html_body)
                    logger.info("Converted HTML body to plain text")

                results.append({
                    "id": eid.decode() if isinstance(eid, bytes) else str(eid),
                    "from": from_decoded,
                    "to": msg.get("To", ""),
                    "subject": subject_decoded,
                    "date": msg.get("Date", ""),
                    "body": body if body else "",
                    "body_preview": body[:500] if body else ""
                })
                logger.info(f"  Result: {subject_decoded} (from: {from_decoded})")

            mail.logout()
            logger.info(f"Returning {len(results)} emails")

            yield self.create_json_message({
                "total_found": len(results),
                "emails": results
            })

        except Exception as e:
            logger.error(f"Search failed: {e}")
            yield self.create_json_message({
                "error": f"Failed to search emails: {str(e)}"
            })
        finally:
            if mail:
                try:
                    mail.logout()
                except Exception:
                    pass
