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

"""Factory for creating scholarly database providers."""

from typing import Dict, Any, Optional
from .scholarly_database import ScholarlyDatabaseProvider
from .semantic_scholar import SemanticScholarProvider
from .openalex import OpenAlexProvider
from ..log import log


class ScholarlyDatabaseFactory:
    """Factory for creating scholarly database provider instances."""

    # Available providers
    PROVIDERS = {
        "semantic_scholar": SemanticScholarProvider,
        "semanticscholar": SemanticScholarProvider,  # Alias for backward compatibility
        "openalex": OpenAlexProvider,
    }

    @classmethod
    def create_provider(
        cls,
        provider_name: str,
        config: Dict[str, Any]
    ) -> Optional[ScholarlyDatabaseProvider]:
        """
        Create a scholarly database provider instance.

        Args:
            provider_name: Name of the provider (semantic_scholar, openalex)
            config: Provider configuration dictionary

        Returns:
            Provider instance if successful, None otherwise
        """
        # Normalize provider name
        provider_name = provider_name.lower().replace("-", "_")

        # Get provider class
        provider_class = cls.PROVIDERS.get(provider_name)
        if not provider_class:
            log.error(f"Unknown scholarly database provider: {provider_name}")
            log.info(f"Available providers: {', '.join(cls.PROVIDERS.keys())}")
            return None

        # Create provider instance
        try:
            provider = provider_class(config)

            # Check if provider is configured
            if not provider.is_configured():
                log.error(f"{provider.name} is not properly configured")
                if provider.requires_api_key:
                    log.error("API key is required but not provided")
                return None
            return provider

        except Exception as e:
            log.error(f"Failed to create {provider_name} provider: {e}")
            return None

    @classmethod
    def list_providers(cls) -> Dict[str, bool]:
        """
        List available providers and their API key requirements.

        Returns:
            Dictionary mapping provider names to whether they require API keys
        """
        result = {}
        for name, provider_class in cls.PROVIDERS.items():
            # Create temporary instance to check requirements
            temp = provider_class({})
            result[name] = temp.requires_api_key
        return result

