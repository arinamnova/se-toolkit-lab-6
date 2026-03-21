#!/usr/bin/env python3
"""CLI agent with tools and agentic loop for wiki-based Q&A.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON to stdout: {"answer": "...", "source": "...", "tool_calls": [...]}

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


# Project root for path validation
PROJECT_ROOT = Path(__file__).parent.resolve()

# Maximum tool calls per question
MAX_TOOL_CALLS = 10


def load_settings() -> Settings:
    """Load and validate settings."""
    try:
        return Settings()
    except Exception as e:
        print(f"Error loading settings: {e}", file=sys.stderr)
        sys.exit(1)


def validate_path(relative_path: str) -> Path:
    """Validate and resolve a relative path within the project.

    Args:
        relative_path: Path relative to project root

    Returns:
        Resolved absolute path

    Raises:
        ValueError: If path is outside project directory or contains traversal
    """
    # Reject paths with ..
    if ".." in relative_path:
        raise ValueError(f"Path traversal not allowed: {relative_path}")

    # Resolve the full path
    full_path = (PROJECT_ROOT / relative_path).resolve()

    # Check it's within project root
    if not str(full_path).startswith(str(PROJECT_ROOT)):
        raise ValueError(f"Path outside project directory: {relative_path}")

    return full_path


def read_file(path: str) -> str:
    """Read a file from the project repository.

    Args:
        path: Relative path from project root

    Returns:
        File contents as a string, or an error message
    """
    try:
        full_path = validate_path(path)

        if not full_path.exists():
            return f"Error: File not found: {path}"

        if not full_path.is_file():
            return f"Error: Not a file: {path}"

        return full_path.read_text(encoding="utf-8")
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error reading file: {e}"


def list_files(path: str) -> str:
    """List files and directories at a given path.

    Args:
        path: Relative directory path from project root

    Returns:
        Newline-separated listing of entries, or an error message
    """
    try:
        full_path = validate_path(path)

        if not full_path.exists():
            return f"Error: Directory not found: {path}"

        if not full_path.is_dir():
            return f"Error: Not a directory: {path}"

        entries = sorted([entry.name for entry in full_path.iterdir()])
        return "\n".join(entries)
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error listing directory: {e}"


# Tool definitions for LLM function calling
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the project repository",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories at a given path",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path from project root",
                    }
                },
                "required": ["path"],
            },
        },
    },
]

# Map tool names to functions
TOOL_FUNCTIONS = {
    "read_file": read_file,
    "list_files": list_files,
}

# System prompt for the agent
SYSTEM_PROMPT = """You are a helpful assistant that answers questions using the project wiki.
You have access to two tools:
- list_files: List files in a directory
- read_file: Read the contents of a file

To answer a question:
1. First use list_files to explore the wiki directory structure if needed
2. Use read_file to read relevant wiki files
3. Find the answer in the file contents
4. Provide the answer with a source reference (file path and section anchor)

Always include the source field in your final answer. The source should be in the format: wiki/filename.md#section-anchor

If the question is about git, check files like git-vscode.md or git-workflow.md.
If the question is about docker, check docker.md or docker-compose.md.
Be specific about which file and section contains the answer."""


def call_llm(messages: list, settings: Settings, tools: list | None = None) -> dict:
    """Call the LLM API and return the response.

    Args:
        messages: List of message dicts for the conversation
        settings: Loaded settings with API credentials
        tools: Optional list of tool definitions for function calling

    Returns:
        The LLM response dict

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
        "messages": messages,
        "temperature": 0.7,
    }

    if tools:
        payload["tools"] = tools

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
        print(
            f"Error: LLM API returned {e.response.status_code}: {e.response.text[:200]}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        data = response.json()
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON response from LLM API", file=sys.stderr)
        sys.exit(1)

    return data


def execute_tool_call(tool_call: dict) -> dict:
    """Execute a single tool call and return the result.

    Args:
        tool_call: Dict with 'function' containing 'name' and 'arguments'

    Returns:
        Dict with 'tool', 'args', and 'result'
    """
    function = tool_call["function"]
    tool_name = function["name"]

    try:
        args = json.loads(function["arguments"])
    except json.JSONDecodeError:
        return {
            "tool": tool_name,
            "args": function["arguments"],
            "result": f"Error: Invalid JSON arguments: {function['arguments']}",
        }

    print(f"Executing tool: {tool_name}({args})", file=sys.stderr)

    if tool_name not in TOOL_FUNCTIONS:
        return {
            "tool": tool_name,
            "args": args,
            "result": f"Error: Unknown tool: {tool_name}",
        }

    try:
        result = TOOL_FUNCTIONS[tool_name](**args)
    except TypeError as e:
        result = f"Error: Invalid arguments for {tool_name}: {e}"
    except Exception as e:
        result = f"Error executing {tool_name}: {e}"

    return {
        "tool": tool_name,
        "args": args,
        "result": result,
    }


def run_agentic_loop(question: str, settings: Settings) -> tuple[str, str, list]:
    """Run the agentic loop to answer a question.

    Args:
        question: The user's question
        settings: Loaded settings with API credentials

    Returns:
        Tuple of (answer, source, tool_calls)
    """
    # Initialize conversation with system prompt and user question
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    tool_calls = []
    iteration = 0

    while iteration < MAX_TOOL_CALLS:
        iteration += 1
        print(f"\n--- Iteration {iteration} ---", file=sys.stderr)

        # Call LLM with tools
        response = call_llm(messages, settings, tools=TOOLS)

        # Extract the assistant message
        try:
            assistant_message = response["choices"][0]["message"]
        except (KeyError, IndexError) as e:
            print(f"Error: Unexpected response format: {e}", file=sys.stderr)
            print(f"Response: {response}", file=sys.stderr)
            sys.exit(1)

        # Check for tool calls
        tool_calls_in_response = assistant_message.get("tool_calls", [])

        if not tool_calls_in_response:
            # No tool calls - this is the final answer
            print("LLM returned final answer (no tool calls)", file=sys.stderr)
            answer = assistant_message.get("content", "")

            # Try to extract source from the answer
            source = extract_source_from_answer(answer)

            return answer, source, tool_calls

        # Execute each tool call
        for tool_call in tool_calls_in_response:
            result = execute_tool_call(tool_call)
            tool_calls.append(result)

            print(f"Tool result: {result['result'][:100]}...", file=sys.stderr)

            # Add assistant message with tool call to conversation
            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [tool_call],
                }
            )

            # Add tool result as a separate message
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "content": result["result"],
                }
            )

    # Max iterations reached
    print(f"Warning: Reached maximum tool calls ({MAX_TOOL_CALLS})", file=sys.stderr)

    # Try to get an answer from the last response
    answer = assistant_message.get("content", "")
    source = extract_source_from_answer(answer)

    return answer, source, tool_calls


def extract_source_from_answer(answer: str) -> str:
    """Extract a source reference from the answer text.

    Looks for patterns like:
    - wiki/filename.md#section
    - See wiki/filename.md
    - (wiki/filename.md)

    Args:
        answer: The answer text

    Returns:
        Extracted source reference, or empty string if not found
    """
    import re

    # Look for wiki file references with anchors
    pattern = r"wiki/[\w-]+\.md(?:#[\w-]+)?"
    match = re.search(pattern, answer)

    if match:
        return match.group(0)

    return ""


def main() -> None:
    """Main entry point."""
    # Check command-line arguments
    if len(sys.argv) < 2:
        print('Usage: uv run agent.py "Your question here"', file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]

    # Load settings
    settings = load_settings()

    # Run the agentic loop
    answer, source, tool_calls = run_agentic_loop(question, settings)

    # Output structured JSON
    output = {
        "answer": answer,
        "source": source,
        "tool_calls": tool_calls,
    }

    print(json.dumps(output))


if __name__ == "__main__":
    main()
