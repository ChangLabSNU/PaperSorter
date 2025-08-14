#!/usr/bin/env python3
#
# Copyright (c) 2024-2025 Seoul National University
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

"""SMTP client wrapper for sending email notifications."""

import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from typing import Optional, Dict, Any
import time

logger = logging.getLogger(__name__)


class SMTPClient:
    """SMTP client for sending email notifications."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize SMTP client with configuration.

        Args:
            config: Dictionary containing SMTP and email settings
                - smtp.host: SMTP server hostname
                - smtp.port: SMTP server port (default: 25)
                - smtp.use_tls: Enable STARTTLS (default: False)
                - smtp.use_ssl: Enable SSL/TLS (default: False)
                - smtp.timeout: Connection timeout in seconds (default: 30)
                - email.from_address: Sender email address
                - email.from_name: Sender display name (optional)
        """
        self.smtp_config = config.get('smtp', {})
        self.email_config = config.get('email', {})

        # SMTP settings
        self.host = self.smtp_config.get('host', 'localhost')
        self.port = self.smtp_config.get('port', 25)
        self.use_tls = self.smtp_config.get('use_tls', False)
        self.use_ssl = self.smtp_config.get('use_ssl', False)
        self.timeout = self.smtp_config.get('timeout', 30)

        # Email settings
        self.from_address = self.email_config.get('from_address', 'papersorter@localhost')
        self.from_name = self.email_config.get('from_name', 'PaperSorter')

    def send_email(
        self,
        recipient: str,
        subject: str,
        html_content: str,
        text_content: str,
        retry_count: int = 3,
        retry_delay: int = 5
    ) -> bool:
        """Send an email with both HTML and plain text content.

        Args:
            recipient: Recipient email address
            subject: Email subject
            html_content: HTML version of the email body
            text_content: Plain text version of the email body
            retry_count: Number of retry attempts on failure
            retry_delay: Delay in seconds between retries

        Returns:
            True if email was sent successfully, False otherwise
        """
        for attempt in range(retry_count):
            try:
                # Create message
                msg = self._create_message(recipient, subject, html_content, text_content)

                # Send email
                self._send_message(msg, recipient)

                logger.info(f"Email sent successfully to {recipient}")
                return True

            except Exception as e:
                logger.error(f"Failed to send email (attempt {attempt + 1}/{retry_count}): {e}")
                if attempt < retry_count - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff

        logger.error(f"Failed to send email to {recipient} after {retry_count} attempts")
        return False

    def _create_message(
        self,
        recipient: str,
        subject: str,
        html_content: str,
        text_content: str
    ) -> MIMEMultipart:
        """Create a MIME multipart message.

        Args:
            recipient: Recipient email address
            subject: Email subject
            html_content: HTML version of the email body
            text_content: Plain text version of the email body

        Returns:
            MIMEMultipart message object
        """
        # Create message container
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{self.from_name} <{self.from_address}>" if self.from_name else self.from_address
        msg['To'] = recipient
        msg['Date'] = formatdate(localtime=True)
        msg['Message-ID'] = make_msgid()

        # Create the body parts
        text_part = MIMEText(text_content, 'plain', 'utf-8')
        html_part = MIMEText(html_content, 'html', 'utf-8')

        # Attach parts
        # Note: The last part is preferred by email clients
        msg.attach(text_part)
        msg.attach(html_part)

        return msg

    def _send_message(self, msg: MIMEMultipart, recipient: str):
        """Send the message via SMTP.

        Args:
            msg: MIMEMultipart message to send
            recipient: Recipient email address

        Raises:
            Exception: If sending fails
        """
        smtp = None
        try:
            # Create SMTP connection
            if self.use_ssl:
                smtp = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout)
            else:
                smtp = smtplib.SMTP(self.host, self.port, timeout=self.timeout)

            # Enable TLS if requested
            if self.use_tls and not self.use_ssl:
                smtp.starttls()

            # Send the message
            smtp.send_message(msg)

        finally:
            if smtp:
                try:
                    smtp.quit()
                except:
                    pass  # Ignore errors when closing

    def test_connection(self) -> bool:
        """Test SMTP connection.

        Returns:
            True if connection successful, False otherwise
        """
        smtp = None
        try:
            if self.use_ssl:
                smtp = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout)
            else:
                smtp = smtplib.SMTP(self.host, self.port, timeout=self.timeout)

            if self.use_tls and not self.use_ssl:
                smtp.starttls()

            # Get server info
            code, message = smtp.noop()
            if code == 250:
                logger.info(f"SMTP connection test successful: {message.decode()}")
                return True
            else:
                logger.error(f"SMTP connection test failed: {code} {message.decode()}")
                return False

        except Exception as e:
            logger.error(f"SMTP connection test failed: {e}")
            return False
        finally:
            if smtp:
                try:
                    smtp.quit()
                except:
                    pass