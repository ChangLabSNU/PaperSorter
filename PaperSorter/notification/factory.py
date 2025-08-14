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

"""Factory for creating notification providers based on webhook URL."""

from urllib.parse import urlparse
from ..log import log
from .slack import SlackProvider
from .discord import DiscordProvider


def create_notification_provider(webhook_url):
    """Create appropriate notification provider based on webhook URL.

    Automatically detects the webhook type based on the hostname:
    - Hostnames ending with 'slack.com' -> SlackProvider
    - Hostnames ending with 'discord.com' or 'discordapp.com' -> DiscordProvider

    Args:
        webhook_url: The webhook URL to analyze

    Returns:
        NotificationProvider: Appropriate provider instance

    Raises:
        ValueError: If webhook URL is invalid or empty
    """
    if not webhook_url:
        raise ValueError("Webhook URL cannot be empty")

    # Parse the URL to get hostname
    try:
        parsed = urlparse(webhook_url)
        hostname = parsed.hostname or ""
    except Exception as e:
        raise ValueError(f"Invalid webhook URL: {e}")

    if not hostname:
        raise ValueError(f"Could not extract hostname from URL: {webhook_url}")

    # Determine provider based on hostname
    hostname_lower = hostname.lower()

    if hostname_lower.endswith("slack.com"):
        log.debug(f"Detected Slack webhook: {hostname}")
        return SlackProvider(webhook_url)
    elif hostname_lower.endswith("discord.com") or hostname_lower.endswith(
        "discordapp.com"
    ):
        log.debug(f"Detected Discord webhook: {hostname}")
        return DiscordProvider(webhook_url)
    else:
        # Default to Slack for backward compatibility
        log.warning(
            f"Unknown webhook hostname '{hostname}', defaulting to Slack provider"
        )
        return SlackProvider(webhook_url)
