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

import click
import sys
import yaml
from typing import Optional
from ..utils.email import SMTPClient
from ..log import initialize_logging


@click.group()
@click.option("--config", "-c", default="./config.yml", help="Path to configuration file")
@click.option("--log-file", help="Path to log file")
@click.option("--quiet", "-q", is_flag=True, help="Suppress informational output")
@click.pass_context
def main(ctx, config, log_file, quiet):
    """Test various PaperSorter system components."""
    # Configure logging
    initialize_logging("test", log_file, quiet)

    # Store config path for subcommands
    ctx.ensure_object(dict)
    ctx.obj['config_path'] = config
    ctx.obj['quiet'] = quiet


@main.command('smtp')
@click.option('--recipient', '-r', help='Test recipient email address')
@click.option('--subject', '-s', default='PaperSorter SMTP Test', help='Test email subject')
@click.option('--verbose', '-v', is_flag=True, help='Show detailed connection information')
@click.pass_context
def smtp(ctx, recipient: Optional[str], subject: str, verbose: bool):
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
    config_path = ctx.obj['config_path']
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        click.echo(f"Error loading configuration from {config_path}: {e}", err=True)
        sys.exit(1)

    # Check if SMTP is configured
    if 'smtp' not in config:
        click.echo("Error: No SMTP configuration found in config file", err=True)
        click.echo("\nPlease add SMTP configuration to your config.yml:", err=True)
        click.echo("""
smtp:
  provider: gmail  # or outlook, yahoo, custom
  username: your-email@gmail.com
  password: your-app-password
        """, err=True)
        sys.exit(1)

    # Initialize SMTP client
    try:
        smtp_client = SMTPClient(config)
    except Exception as e:
        click.echo(f"Error initializing SMTP client: {e}", err=True)
        sys.exit(1)

    # Show connection information if verbose
    if verbose:
        info = smtp_client.get_connection_info()
        click.echo("\n=== SMTP Configuration ===")
        click.echo(f"Host: {info['host']}")
        click.echo(f"Port: {info['port']}")
        click.echo(f"Encryption: {info['encryption']}")
        click.echo(f"Authentication: {'Yes' if info['authentication'] else 'No'}")
        if info['username']:
            click.echo(f"Username: {info['username']}")
        click.echo(f"From Address: {info['from_address']}")
        click.echo(f"From Name: {info['from_name']}")
        click.echo()

    # Test connection
    click.echo("Testing SMTP connection...")
    if smtp_client.test_connection():
        click.echo("✓ SMTP connection successful")

        # If recipient provided, send test email
        if recipient:
            click.echo(f"\nSending test email to {recipient}...")

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
                click.echo(f"✓ Test email sent successfully to {recipient}")
                click.echo("\nSMTP configuration is working correctly!")
            else:
                click.echo("✗ Failed to send test email", err=True)
                sys.exit(1)
    else:
        click.echo("✗ SMTP connection failed", err=True)
        click.echo("\nPlease check your SMTP configuration:", err=True)

        # Provide helpful troubleshooting tips
        smtp_config = config.get('smtp', {})
        provider = smtp_config.get('provider')

        if provider == 'gmail':
            click.echo("""
Gmail troubleshooting:
1. Enable 2-factor authentication in your Google account
2. Generate an app-specific password at https://myaccount.google.com/apppasswords
3. Use the app password (not your regular password) in the configuration
            """, err=True)
        elif provider == 'outlook':
            click.echo("""
Outlook troubleshooting:
1. Enable 2-factor authentication in your Microsoft account
2. Generate an app password at https://account.microsoft.com/security
3. Use the app password (not your regular password) in the configuration
            """, err=True)
        elif provider == 'yahoo':
            click.echo("""
Yahoo troubleshooting:
1. Enable 2-step verification in your Yahoo account
2. Generate an app password at https://login.yahoo.com/myaccount/security
3. Use the app password (not your regular password) in the configuration
            """, err=True)

        sys.exit(1)


# Make the test command available as a task
test = main