## email_pro

**Author:** dq
**Version:** 0.0.1
**Type:** tool

### Description

A Dify plugin that provides email tools for searching and sending emails via SMTP/IMAP protocols. It includes two tools:

- **Send Email**: Send emails through a configurable SMTP server with support for TLS, SSL, and no encryption modes.
- **Search Email**: Search and retrieve emails from a configured mailbox using IMAP, with filtering by sender, subject keyword, date range, and mail folder.

### Setup

1. Install the plugin in your Dify instance.
2. Configure the following credentials in the plugin settings:
   - **SMTP Server**: Your SMTP host (e.g. `smtp.gmail.com`)
   - **SMTP Port**: Your SMTP port (e.g. `587` for TLS, `465` for SSL)
   - **Email Address**: Your email address for authentication
   - **Email Password / App Password**: Your email password or an app-specific password
   - **Encryption Method**: Choose START TLS, SSL, or NONE

> For Gmail, you need to generate an [App Password](https://support.google.com/accounts/answer/185833).
> For QQ Mail, use an authorization code instead of your login password.

### Tools

#### Send Email
Send an email to a specified recipient with subject and body content. Returns structured output including status, sender, recipient, subject, and timestamp.

#### Search Email
Search emails by folder, sender, subject keyword, and date range. Returns matching emails with full details including body content.

### Usage

After configuration, you can use these tools in Dify workflows:

1. **Send Email**: Provide recipient email, subject, and body content.
2. **Search Email**: Optionally filter by folder (default: INBOX), sender address, subject keyword, date range (last N days), and max results.
