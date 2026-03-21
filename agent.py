#!/usr/bin/env python3
"""CLI agent with tools and agentic loop for wiki and API-based Q&A.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON to stdout: {"answer": "...", "source": "...", "tool_calls": [...]}

Environment:
    Reads from .env.agent.secret:
    - LLM_API_KEY: API key for the LLM provider
    - LLM_API_BASE_URL: Base URL of the LLM API
    - LLM_API_MODEL: Model name to use

    Reads from .env.docker.secret (optional, for query_api):
    - LMS_API_KEY: API key for backend authentication
    - AGENT_API_BASE_URL: Base URL for backend API (default: http://localhost:42002)
"""

import json
import os
import re
import sys
from pathlib import Path

import httpx
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Load settings from environment files.

    Reads LLM settings from .env.agent.secret and backend settings from .env.docker.secret.
    Also reads from environment variables for autochecker compatibility.
    """

    # LLM settings
    llm_api_key: str
    llm_api_base_url: str
    llm_api_model: str = "coder-model"

    # Backend API settings
    lms_api_key: str = ""
    agent_api_base_url: str = "http://localhost:42002"

    class Config:
        env_file = [".env.agent.secret", ".env.docker.secret"]
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


def query_api(method: str, path: str, body: str | None = None) -> str:
    """Call the backend LMS API and return the response.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: API endpoint path (e.g., /items/)
        body: Optional JSON request body for POST/PUT requests

    Returns:
        JSON string with status_code and body, or an error message
    """
    # Load LMS API key from environment
    lms_api_key = os.environ.get("LMS_API_KEY", "")
    api_base_url = os.environ.get("AGENT_API_BASE_URL", "http://localhost:42002")

    if not lms_api_key:
        return "Error: LMS_API_KEY not set in environment"

    # Build the URL
    url = f"{api_base_url}{path}"

    headers = {
        "X-API-Key": lms_api_key,
        "Content-Type": "application/json",
    }

    print(f"Calling API: {method} {url}", file=sys.stderr)

    try:
        if method.upper() == "GET":
            response = httpx.get(url, headers=headers, timeout=30.0)
        elif method.upper() == "POST":
            response = httpx.post(
                url,
                headers=headers,
                json=json.loads(body) if body else {},
                timeout=30.0,
            )
        elif method.upper() == "PUT":
            response = httpx.put(
                url,
                headers=headers,
                json=json.loads(body) if body else {},
                timeout=30.0,
            )
        elif method.upper() == "DELETE":
            response = httpx.delete(url, headers=headers, timeout=30.0)
        else:
            return f"Error: Unsupported HTTP method: {method}"

        result = {
            "status_code": response.status_code,
            "body": response.text,
        }

        # Try to parse body as JSON for cleaner output
        try:
            result["body"] = response.json()
        except (json.JSONDecodeError, ValueError):
            pass

        return json.dumps(result)

    except httpx.TimeoutException:
        return f"Error: API request timed out for {url}"
    except httpx.ConnectError as e:
        return f"Error: Cannot connect to API at {url}: {e}"
    except httpx.RequestError as e:
        return f"Error: API request failed: {e}"
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON body: {e}"
    except Exception as e:
        return f"Error querying API: {e}"


# Tool definitions for LLM function calling
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the project repository. Use for wiki documentation or source code questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root (e.g., wiki/git.md or backend/app/main.py)",
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
            "description": "List files and directories at a given path. Use to explore directory structure.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path from project root (e.g., wiki or backend/app/routers)",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_api",
            "description": "Call the backend LMS API to query data or test endpoints. Use for questions about database contents, item counts, scores, API status codes, or error responses. NOT for wiki or source code questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "description": "HTTP method (GET, POST, PUT, DELETE)",
                    },
                    "path": {
                        "type": "string",
                        "description": "API endpoint path (e.g., /items/, /analytics/completion-rate)",
                    },
                    "body": {
                        "type": "string",
                        "description": "JSON request body (optional, for POST/PUT requests)",
                    },
                },
                "required": ["method", "path"],
            },
        },
    },
]

# Map tool names to functions
TOOL_FUNCTIONS = {
    "read_file": read_file,
    "list_files": list_files,
    "query_api": query_api,
}

# System prompt for the agent
SYSTEM_PROMPT = """You are a helpful assistant that answers questions using:
1. The project wiki (for documentation)
2. The source code (for implementation details)
3. The backend API (for live data)

You have access to three tools:
- list_files: List files in a directory
- read_file: Read the contents of a file
- query_api: Call the backend API to query data or test endpoints

Tool selection guide:
- For wiki/documentation questions (git, docker, ssh, etc.) → use list_files and read_file on wiki/
- For source code questions (framework, architecture, code structure) → use list_files and read_file on backend/, agent.py, docker-compose.yml, etc.
- For data questions (counts, scores, records, "how many") → use query_api with GET
- For API behavior questions (status codes, errors, authentication) → use query_api

When using query_api:
- Use GET for retrieving data (most common)
- Use POST for creating data
- Check the status_code in the response
- For authentication errors (401, 403), note that the API requires an API key

Always provide a source reference when applicable:
- Wiki files: wiki/filename.md#section-anchor
- Source files: path/to/file.py (or path/to/file.py:function_name if you can identify a function)
- API responses: API endpoint path (e.g., GET /items/)

For complex questions:
1. First explore with list_files if you're unsure where to look
2. Read relevant files with read_file
3. For API questions, query the endpoint and analyze the response
4. If you get an error from the API, read the source code to diagnose the bug

Be specific and cite your sources."""


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
            answer = assistant_message.get("content") or ""

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
    answer = assistant_message.get("content") or ""
    source = extract_source_from_answer(answer)

    return answer, source, tool_calls


def extract_source_from_answer(answer: str) -> str:
    """Extract a source reference from the answer text.

    Looks for patterns like:
    - wiki/filename.md#section
    - path/to/file.py
    - GET /api/endpoint

    Args:
        answer: The answer text

    Returns:
        Extracted source reference, or empty string if not found
    """
    # Look for wiki file references with anchors
    wiki_pattern = r"wiki/[\w-]+\.md(?:#[\w-]+)?"
    match = re.search(wiki_pattern, answer)
    if match:
        return match.group(0)

    # Look for Python file references
    py_pattern = r"[\w./]+\.py(?::[\w_]+)?"
    match = re.search(py_pattern, answer)
    if match:
        return match.group(0)

    # Look for API endpoint references
    api_pattern = r"(?:GET|POST|PUT|DELETE)\s+/[\w./-]+"
    match = re.search(api_pattern, answer)
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
