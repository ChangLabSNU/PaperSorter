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

"""Utilities for handling broadcast hour restrictions."""

from datetime import datetime
from typing import Optional, Set


def parse_broadcast_hours(hours_str: Optional[str]) -> Set[int]:
    """Parse broadcast hours string into a set of allowed hours.

    Args:
        hours_str: Comma-separated hour ranges like "5-7,10,15-17" or None

    Returns:
        Set of hours (0-23) when broadcasting is allowed.
        Empty set means no restrictions (all hours allowed).
    """
    if not hours_str:
        return set()  # No restrictions

    allowed_hours = set()

    for part in hours_str.split(','):
        part = part.strip()
        if not part:
            continue

        if '-' in part:
            # Range like "5-7"
            try:
                start, end = part.split('-')
                start = int(start.strip())
                end = int(end.strip())

                # Validate range
                if 0 <= start <= 23 and 0 <= end <= 23:
                    # Handle wrap-around (e.g., "22-2" means 22,23,0,1,2)
                    if start <= end:
                        allowed_hours.update(range(start, end + 1))
                    else:
                        allowed_hours.update(range(start, 24))
                        allowed_hours.update(range(0, end + 1))
            except (ValueError, AttributeError):
                # Invalid format, skip this part
                pass
        else:
            # Single hour like "10"
            try:
                hour = int(part.strip())
                if 0 <= hour <= 23:
                    allowed_hours.add(hour)
            except ValueError:
                # Invalid format, skip this part
                pass

    return allowed_hours


def is_broadcast_allowed(hours_str: Optional[str], check_time: Optional[datetime] = None) -> bool:
    """Check if broadcasting is allowed at the given time.

    Args:
        hours_str: Comma-separated hour ranges like "5-7,10,15-17" or None
        check_time: Time to check (defaults to current time)

    Returns:
        True if broadcasting is allowed at the given time
    """
    if not hours_str:
        return True  # No restrictions

    if check_time is None:
        check_time = datetime.now()

    allowed_hours = parse_broadcast_hours(hours_str)
    if not allowed_hours:
        return True  # No restrictions or invalid format

    current_hour = check_time.hour
    return current_hour in allowed_hours


def format_broadcast_hours(hours: Set[int]) -> str:
    """Format a set of hours into a compact string representation.

    Args:
        hours: Set of hours (0-23)

    Returns:
        Comma-separated hour ranges like "5-7,10,15-17"
    """
    if not hours:
        return ""

    sorted_hours = sorted(hours)
    ranges = []
    start = sorted_hours[0]
    end = sorted_hours[0]

    for hour in sorted_hours[1:]:
        if hour == end + 1:
            end = hour
        else:
            if start == end:
                ranges.append(str(start))
            else:
                ranges.append(f"{start}-{end}")
            start = hour
            end = hour

    # Add the last range
    if start == end:
        ranges.append(str(start))
    else:
        ranges.append(f"{start}-{end}")

    return ",".join(ranges)


def hours_to_checkbox_array(hours_str: Optional[str]) -> list:
    """Convert hours string to a 24-element boolean array for UI checkboxes.

    Args:
        hours_str: Comma-separated hour ranges or None

    Returns:
        List of 24 booleans, where True means the hour is allowed
    """
    if not hours_str:
        # NULL/None means no restrictions - show all hours as checked
        return [True] * 24

    allowed_hours = parse_broadcast_hours(hours_str)
    if not allowed_hours:
        # Empty string or no valid hours means no broadcasting allowed
        return [False] * 24

    return [hour in allowed_hours for hour in range(24)]


def checkbox_array_to_hours(checkboxes: list) -> Optional[str]:
    """Convert a 24-element boolean array to hours string.

    Args:
        checkboxes: List of 24 booleans

    Returns:
        Comma-separated hour ranges or None if all hours are selected (24/7)
    """
    if len(checkboxes) != 24:
        return None

    # If all hours are selected, return None (no restrictions = 24/7)
    if all(checkboxes):
        return None

    # If no hours are selected, return a special marker that prevents all broadcasting
    if not any(checkboxes):
        return ""  # Empty string means no broadcasting allowed

    # Convert to set of selected hours
    selected_hours = {i for i, checked in enumerate(checkboxes) if checked}

    return format_broadcast_hours(selected_hours)
