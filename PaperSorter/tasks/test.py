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

"""Test commands for PaperSorter system components."""

import sys
import yaml
from typing import Optional
import argparse
from ..cli.base import BaseCommand, registry
from ..utils.email import SMTPClient
from ..log import initialize_logging


class TestCommand(BaseCommand):
    """Test various PaperSorter system components."""

    name = 'test'
    help = 'Test various PaperSorter system components'

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add test subcommands."""
        subparsers = parser.add_subparsers(
            dest='subcommand',
            help='Available test commands'
        )

        # Add smtp subcommand
        smtp_parser = subparsers.add_parser(
            'smtp',
            help='Test SMTP email configuration'
        )
        smtp_parser.add_argument(
            '--recipient', '-r',
            help='Test recipient email address'
        )
        smtp_parser.add_argument(
            '--subject', '-s',
            default='PaperSorter SMTP Test',
            help='Test email subject'
        )
        smtp_parser.add_argument(
            '--verbose', '-v',
            action='store_true',
            help='Show detailed connection information'
        )

    def handle(self, args: argparse.Namespace, context) -> int:
        """Execute the test command."""
        initialize_logging('test', args.log_file, args.quiet)

        if args.subcommand == 'smtp':
            try:
                return test_smtp(
                    config_path=args.config,
                    recipient=args.recipient,
                    subject=args.subject,
                    verbose=args.verbose,
                    quiet=args.quiet
                )
            except SystemExit as e:
                return e.code if e.code else 1
            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)
                return 1
        else:
            print("Please specify a subcommand: smtp", file=sys.stderr)
            return 1

# Register the command
registry.register(TestCommand)


def test_smtp(config_path: str, recipient: Optional[str], subject: str, verbose: bool, quiet: bool) -> int:
    """Test SMTP email configuration and optionally send a test email.

    Examples:
        # Test connection only
        papersorter test smtp

        # Test connection and send test email
        papersorter test smtp -r user@example.com

        # Verbose mode with detailed information
        papersorter test smtp -v
    """
    # Load configuration file
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading configuration from {config_path}: {e}", file=sys.stderr)
        return 1

    # Check if SMTP is configured
    if 'smtp' not in config:
        print("Error: No SMTP configuration found in config file", file=sys.stderr)
        print("\nPlease add SMTP configuration to your config.yml:", file=sys.stderr)
        print("""
smtp:
  provider: gmail  # or outlook, yahoo, custom
  username: your-email@gmail.com
  password: your-app-password
        """, file=sys.stderr)
        return 1

    # Initialize SMTP client
    try:
        smtp_client = SMTPClient(config)
    except Exception as e:
        print(f"Error initializing SMTP client: {e}", file=sys.stderr)
        return 1

    # Show connection information if verbose
    if verbose:
        info = smtp_client.get_connection_info()
        print("\n=== SMTP Configuration ===")
        print(f"Host: {info['host']}")
        print(f"Port: {info['port']}")
        print(f"Encryption: {info['encryption']}")
        print(f"Authentication: {'Yes' if info['authentication'] else 'No'}")
        if info['username']:
            print(f"Username: {info['username']}")
        print(f"From Address: {info['from_address']}")
        print(f"From Name: {info['from_name']}")
        print()

    # Test connection
    print("Testing SMTP connection...")
    if smtp_client.test_connection():
        print("✓ SMTP connection successful")

        # If recipient provided, send test email
        if recipient:
            print(f"\nSending test email to {recipient}...")

            # Create test content
            html_content = f"""
            <html>
            <body>
                <h2>PaperSorter SMTP Test</h2>
                <p>This is a test email from your PaperSorter installation.</p>
                <p>If you received this email, your SMTP configuration is working correctly!</p>
                <hr>
                <p><small>Configuration details:</small></p>
                <ul>
                    <li>SMTP Host: {smtp_client.host}</li>
                    <li>SMTP Port: {smtp_client.port}</li>
                    <li>Encryption: {smtp_client.encryption.upper()}</li>
                    <li>Authentication: {'Yes' if smtp_client.username else 'No'}</li>
                </ul>
            </body>
            </html>
            """

            text_content = f"""
PaperSorter SMTP Test

This is a test email from your PaperSorter installation.
If you received this email, your SMTP configuration is working correctly!

Configuration details:
- SMTP Host: {smtp_client.host}
- SMTP Port: {smtp_client.port}
- Encryption: {smtp_client.encryption.upper()}
- Authentication: {'Yes' if smtp_client.username else 'No'}
            """

            # Send test email
            if smtp_client.send_email(recipient, subject, html_content, text_content):
                print(f"✓ Test email sent successfully to {recipient}")
                print("\nSMTP configuration is working correctly!")
                return 0
            else:
                print("✗ Failed to send test email", file=sys.stderr)
                return 1
    else:
        print("✗ SMTP connection failed", file=sys.stderr)
        print("\nPlease check your SMTP configuration:", file=sys.stderr)

        # Provide helpful troubleshooting tips
        smtp_config = config.get('smtp', {})
        provider = smtp_config.get('provider')

        if provider == 'gmail':
            print("""
Gmail troubleshooting:
1. Enable 2-factor authentication in your Google account
2. Generate an app-specific password at https://myaccount.google.com/apppasswords
3. Use the app password (not your regular password) in the configuration
            """, file=sys.stderr)
        elif provider == 'outlook':
            print("""
Outlook troubleshooting:
1. Enable 2-factor authentication in your Microsoft account
2. Generate an app password at https://account.microsoft.com/security
3. Use the app password (not your regular password) in the configuration
            """, file=sys.stderr)
        elif provider == 'yahoo':
            print("""
Yahoo troubleshooting:
1. Enable 2-step verification in your Yahoo account
2. Generate an app password at https://login.yahoo.com/myaccount/security
3. Use the app password (not your regular password) in the configuration
            """, file=sys.stderr)

        return 1

    # If we get here without recipient, connection was successful
    return 0