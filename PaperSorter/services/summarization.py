#!/usr/bin/env python3
"""High-level helpers for LLM-backed article summarization."""

from __future__ import annotations

from typing import Sequence

from ..providers.openai_client import get_openai_client

SUMMARY_PROMPT_TEMPLATE = """You are an expert scientific literature analyst. Analyze the following collection of research articles and provide a focused summary.

{articles}

Start your response directly with the numbered sections below. Do not include any introductory sentences like "Here is my analysis" or "Based on the provided articles". Do not repeat the format instructions (like "2-3 sentences" or "3-4 bullet points") in your output. Begin immediately with:

1. **Common Themes**: Identify the main research areas connecting these articles in 2-3 sentences.

2. **Key Topics**: List the most significant concepts, methods, or findings that appear across multiple papers as 3-4 bullet points.

3. **Unique Contributions**: For each article, briefly state what distinguishes it from the others in one sentence. Reference articles using their author-year format (e.g., "Smith 2023 introduces...").

4. **Future Directions**: Based on these papers, provide 2-3 bullet points on the most promising research opportunities.

Keep your response focused and actionable, using clear Markdown formatting. When referencing specific papers, use the author-year format provided in square brackets for each article."""


class ArticleSummarizer:
    """Wraps OpenAI chat completion calls for article summaries."""

    def __init__(
        self,
        *,
        client,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 8000,
        timeout: float | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout

    @classmethod
    def from_config(cls, config):
        api_config = config.get("summarization_api")
        if not isinstance(api_config, dict):
            return None

        client = get_openai_client("summarization_api", cfg=config, optional=True)
        if client is None:
            return None

        model = api_config.get("model", "gpt-4o-mini")
        temperature = float(api_config.get("temperature", 0.7))
        max_tokens = int(api_config.get("max_tokens", 8000))
        timeout = api_config.get("timeout")
        try:
            timeout_value = float(timeout) if timeout is not None else None
        except (TypeError, ValueError):
            timeout_value = None

        return cls(
            client=client,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout_value,
        )

    def summarize(self, snippets: Sequence[str]) -> str:
        if not snippets:
            raise ValueError("No article snippets provided for summarization")

        articles_text = "\n\n---\n\n".join(snippets)
        prompt = SUMMARY_PROMPT_TEMPLATE.format(articles=articles_text)

        request_kwargs = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an expert at analyzing and summarizing scientific literature.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }
        if self._timeout is not None:
            request_kwargs["timeout"] = self._timeout

        response = self._client.chat.completions.create(**request_kwargs)

        message = response.choices[0].message.content
        if not message:
            raise RuntimeError("Empty response from summarization model")

        if not isinstance(message, str):
            message = str(message)

        return message
