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
from typing import Dict, Any
import time

logger = logging.getLogger(__name__)


class SMTPClient:
    """SMTP client for sending email notifications."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize SMTP client with configuration.

        Args:
            config: Dictionary containing SMTP and email settings:

                SMTP settings:
                - smtp.provider: Provider name (gmail, outlook, yahoo, custom)
                - smtp.username: Username for authentication
                - smtp.password: Password for authentication
                - smtp.host: SMTP server hostname (for custom)
                - smtp.port: SMTP server port (for custom)
                - smtp.encryption: Encryption type (tls, ssl, none)
                - smtp.timeout: Connection timeout in seconds (default: 30)

                Email settings:
                - email.from_address: Sender email address
                - email.from_name: Sender display name (optional)
        """
        self.smtp_config = config.get('smtp', {})
        self.email_config = config.get('email', {})

        # Check for provider-based configuration
        provider = self.smtp_config.get('provider')

        if provider:
            # Provider-based configuration
            self._configure_provider(provider)
        else:
            # Direct configuration
            self.host = self.smtp_config.get('host', 'localhost')
            self.port = self.smtp_config.get('port', 25)
            self.encryption = self.smtp_config.get('encryption', 'none').lower()
            self.username = self.smtp_config.get('username')
            self.password = self.smtp_config.get('password')

        # Common settings
        self.timeout = self.smtp_config.get('timeout', 30)

        # Email settings
        self.from_address = self.email_config.get('from_address', 'papersorter@localhost')
        self.from_name = self.email_config.get('from_name', 'PaperSorter')

    def _configure_provider(self, provider: str):
        """Configure SMTP settings based on provider.

        Args:
            provider: Provider name (gmail, outlook, yahoo, custom)
        """
        # Provider-specific settings
        provider_configs = {
            'gmail': {
                'host': 'smtp.gmail.com',
                'port': 587,
                'encryption': 'tls',
            },
            'outlook': {
                'host': 'smtp-mail.outlook.com',
                'port': 587,
                'encryption': 'tls',
            },
            'yahoo': {
                'host': 'smtp.mail.yahoo.com',
                'port': 587,
                'encryption': 'tls',
            },
        }

        if provider in provider_configs:
            # Use predefined provider settings
            config = provider_configs[provider]
            self.host = config['host']
            self.port = config['port']
            self.encryption = config['encryption']

            # Get authentication credentials
            self.username = self.smtp_config.get('username')
            self.password = self.smtp_config.get('password')

            if not self.username or not self.password:
                raise ValueError(f"Provider '{provider}' requires username and password")

        elif provider == 'custom':
            # Custom SMTP configuration
            self.host = self.smtp_config.get('host')
            self.port = self.smtp_config.get('port', 587)

            if not self.host:
                raise ValueError("Custom provider requires 'host' to be specified")

            # Get encryption setting
            self.encryption = self.smtp_config.get('encryption', 'tls').lower()

            # Optional authentication for custom provider
            self.username = self.smtp_config.get('username')
            self.password = self.smtp_config.get('password')
        else:
            raise ValueError(f"Unknown SMTP provider: {provider}")

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
            # Create SMTP connection based on encryption type
            if self.encryption == 'ssl':
                smtp = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout)
            else:
                smtp = smtplib.SMTP(self.host, self.port, timeout=self.timeout)

            # Enable STARTTLS if using TLS encryption
            if self.encryption == 'tls':
                smtp.starttls()

            # Authenticate if credentials are provided
            if self.username and self.password:
                smtp.login(self.username, self.password)

            # Send the message
            smtp.send_message(msg)

        finally:
            if smtp:
                try:
                    smtp.quit()
                except Exception:
                    pass  # Ignore errors when closing

    def test_connection(self) -> bool:
        """Test SMTP connection.

        Returns:
            True if connection successful, False otherwise
        """
        smtp = None
        try:
            # Create SMTP connection based on encryption type
            if self.encryption == 'ssl':
                smtp = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout)
            else:
                smtp = smtplib.SMTP(self.host, self.port, timeout=self.timeout)

            # Enable STARTTLS if using TLS encryption
            if self.encryption == 'tls':
                smtp.starttls()

            # Authenticate if credentials are provided
            if self.username and self.password:
                smtp.login(self.username, self.password)
                logger.info(f"SMTP authentication successful for {self.username}")

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
                except Exception:
                    pass

    def get_connection_info(self) -> Dict[str, Any]:
        """Get current SMTP connection information.

        Returns:
            Dictionary with connection details
        """
        return {
            'host': self.host,
            'port': self.port,
            'encryption': self.encryption,
            'authentication': bool(self.username),
            'username': self.username if self.username else None,
            'from_address': self.from_address,
            'from_name': self.from_name,
        }