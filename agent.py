#!/usr/bin/env python3
"""CLI agent that calls an LLM and returns a structured JSON answer.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON to stdout: {"answer": "...", "tool_calls": []}

Environment:
    Reads from .env.agent.secret:
    - LLM_API_KEY: API key for the LLM provider
    - LLM_API_BASE_URL: Base URL of the LLM API
    - LLM_API_MODEL: Model name to use
"""

import json
import sys
from pathlib import Path

import httpx
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Load settings from .env.agent.secret."""

    llm_api_key: str
    llm_api_base_url: str
    llm_api_model: str = "coder-model"

    class Config:
        env_file = ".env.agent.secret"
        env_file_encoding = "utf-8"


def load_settings() -> Settings:
    """Load and validate settings."""
    try:
        return Settings()
    except Exception as e:
        print(f"Error loading settings: {e}", file=sys.stderr)
        sys.exit(1)


def call_lllm(question: str, settings: Settings) -> str:
    """Call the LLM API and return the answer.

    Args:
        question: The user's question
        settings: Loaded settings with API credentials

    Returns:
        The LLM's answer text

    Raises:
        SystemExit: On API errors
    """
    url = f"{settings.llm_api_base_url}/chat/completions"

    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": settings.llm_api_model,
        "messages": [
            {
                "role": "user",
                "content": question,
            }
        ],
        "temperature": 0.7,
    }

    print(f"Calling LLM at {url}...", file=sys.stderr)

    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=60.0)
        response.raise_for_status()
    except httpx.TimeoutException:
        print("Error: LLM API request timed out", file=sys.stderr)
        sys.exit(1)
    except httpx.RequestError as e:
        print(f"Error: Failed to connect to LLM API: {e}", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"Error: LLM API returned {e.response.status_code}: {e.response.text[:200]}", file=sys.stderr)
        sys.exit(1)

    try:
        data = response.json()
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON response from LLM API", file=sys.stderr)
        sys.exit(1)

    # Extract the answer from the response
    try:
        answer = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        print(f"Error: Unexpected response format: {e}", file=sys.stderr)
        print(f"Response: {data}", file=sys.stderr)
        sys.exit(1)

    return answer


def main() -> None:
    """Main entry point."""
    # Check command-line arguments
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py \"Your question here\"", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]

    # Load settings
    settings = load_settings()

    # Call the LLM
    answer = call_lllm(question, settings)

    # Output structured JSON
    output = {
        "answer": answer,
        "tool_calls": [],
    }

    print(json.dumps(output))


if __name__ == "__main__":
    main()
