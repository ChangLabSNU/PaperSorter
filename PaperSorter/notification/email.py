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

"""Email notification provider for sending newsletter digests."""

from datetime import datetime
from jinja2 import Environment, FileSystemLoader
import os
import yaml
from urllib.parse import urlparse
from ..log import log
from ..utils.email import SMTPClient
from .base import NotificationProvider, NotificationError


class EmailProvider(NotificationProvider):
    """Email notification provider that sends batched newsletters."""

    def __init__(self, endpoint_url, config_path="./config.yml"):
        """Initialize email provider.

        Args:
            endpoint_url: mailto: URL with recipient email address
            config_path: Path to configuration file containing SMTP settings
        """
        # Parse mailto URL to get recipient
        if not endpoint_url.startswith("mailto:"):
            raise ValueError(f"Email provider requires mailto: URL, got: {endpoint_url}")

        parsed = urlparse(endpoint_url)
        self.recipient = parsed.path
        if not self.recipient:
            raise ValueError(f"No email address found in URL: {endpoint_url}")

        # Load configuration
        try:
            with open(config_path, "r") as f:
                self.config = yaml.safe_load(f)
        except Exception as e:
            raise ValueError(f"Failed to load configuration from {config_path}: {e}")

        # Initialize SMTP client
        self.smtp_client = SMTPClient(self.config)

        # Set up Jinja2 environment for template rendering
        template_dir = os.path.join(os.path.dirname(__file__), '..', 'templates')
        self.jinja_env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=True
        )

        # Get email configuration
        self.email_config = self.config.get('email', {})
        self.subject_template = self.email_config.get(
            'subject_template',
            'Research Papers Digest - {date:%Y-%m-%d}'
        )

    def send_notifications(self, items, message_options, base_url=None):
        """Send a newsletter email with all items.

        Args:
            items: List of paper dictionaries to include in newsletter
            message_options: Additional options (model_name, channel_name)
            base_url: Base URL for web interface links

        Returns:
            List of (item_id, success) tuples

        Raises:
            NotificationError: If email sending fails
        """
        if not items:
            log.info("No items to send in email newsletter")
            return []

        try:
            # Prepare context for templates
            now = datetime.now()
            context = {
                'papers': items,
                'date': now,
                'base_url': base_url,
                'source_count': len(set(item.get('origin', '') for item in items)),
                'model_name': message_options.get('model_name', 'Default'),
                'channel_name': message_options.get('channel_name', 'PaperSorter'),
            }

            # Generate subject
            subject = self.subject_template.format(date=now)
            if message_options.get('channel_name'):
                subject = f"[{message_options['channel_name']}] {subject}"

            # Render templates
            html_content = self._render_html(context)
            text_content = self._render_text(context)

            # Send email
            success = self.smtp_client.send_email(
                recipient=self.recipient,
                subject=subject,
                html_content=html_content,
                text_content=text_content
            )

            if success:
                log.info(
                    f"Successfully sent newsletter with {len(items)} papers to {self.recipient}"
                )
                # Return success for all items
                return [(item.get('id'), True) for item in items]
            else:
                raise NotificationError(
                    f"Failed to send newsletter to {self.recipient}"
                )

        except Exception as e:
            log.error(f"Error sending email newsletter: {e}")
            raise NotificationError(f"Email sending failed: {e}")

    def _render_html(self, context):
        """Render HTML newsletter template.

        Args:
            context: Template context dictionary

        Returns:
            Rendered HTML content
        """
        try:
            template = self.jinja_env.get_template('email/newsletter.html')
            return template.render(**context)
        except Exception as e:
            log.error(f"Failed to render HTML template: {e}")
            raise NotificationError(f"HTML template rendering failed: {e}")

    def _render_text(self, context):
        """Render plain text newsletter template.

        Args:
            context: Template context dictionary

        Returns:
            Rendered plain text content
        """
        try:
            template = self.jinja_env.get_template('email/newsletter.txt')
            return template.render(**context)
        except Exception as e:
            log.error(f"Failed to render text template: {e}")
            raise NotificationError(f"Text template rendering failed: {e}")