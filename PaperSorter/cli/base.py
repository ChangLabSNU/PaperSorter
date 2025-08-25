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

"""Base command class and registry for PaperSorter CLI."""

import argparse
import sys
from abc import ABC, abstractmethod
from typing import Dict, Type, Optional, Any


class BaseCommand(ABC):
    """Base class for all CLI commands."""

    name: str = None
    help: str = None

    @abstractmethod
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add command-specific arguments to the parser."""
        pass

    @abstractmethod
    def handle(self, args: argparse.Namespace, context: Any) -> int:
        """
        Execute the command.

        Args:
            args: Parsed command-line arguments
            context: Command context with config and utilities

        Returns:
            Exit code (0 for success)
        """
        pass

    def add_common_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add common arguments shared by all commands."""
        parser.add_argument(
            '--config', '-c',
            default='./config.yml',
            help='Database configuration file'
        )
        parser.add_argument(
            '--log-file',
            help='Log file path'
        )
        parser.add_argument(
            '-q', '--quiet',
            action='store_true',
            help='Suppress log output'
        )


class CommandRegistry:
    """Registry for managing CLI commands."""

    def __init__(self):
        self._commands: Dict[str, Type[BaseCommand]] = {}
        self._instances: Dict[str, BaseCommand] = {}

    def register(self, command_class: Type[BaseCommand]) -> None:
        """Register a command class."""
        if not command_class.name:
            raise ValueError(f"Command {command_class.__name__} must have a name")
        self._commands[command_class.name] = command_class

    def get_command(self, name: str) -> Optional[BaseCommand]:
        """Get a command instance by name."""
        if name not in self._instances and name in self._commands:
            command_class = self._commands[name]
            # Check if it's already an instance
            if isinstance(command_class, BaseCommand):
                self._instances[name] = command_class
            else:
                self._instances[name] = command_class()
        return self._instances.get(name)

    def create_subparsers(self, parser: argparse.ArgumentParser) -> None:
        """Create subparsers for all registered commands."""
        subparsers = parser.add_subparsers(
            dest='command',
            help='Available commands',
            metavar='<command>'
        )

        for name, command_class in sorted(self._commands.items()):
            command = self.get_command(name)

            # Replace underscores with hyphens in command names for CLI
            cli_name = name.replace('_', '-')

            subparser = subparsers.add_parser(
                cli_name,
                help=command.help,
                formatter_class=argparse.RawDescriptionHelpFormatter
            )

            # Add common arguments
            command.add_common_arguments(subparser)

            # Add command-specific arguments
            command.add_arguments(subparser)

            # Store the command instance for later execution
            subparser.set_defaults(command_handler=command)

    def list_commands(self) -> list:
        """Return a list of registered command names."""
        return sorted(self._commands.keys())


# Global registry instance
registry = CommandRegistry()