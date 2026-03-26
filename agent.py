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
import warnings
from pathlib import Path

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict

# Suppress Pydantic deprecation warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)


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

    model_config = SettingsConfigDict(
        env_file=[".env.agent.secret", ".env.docker.secret"],
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore extra fields in .env files
    )


# Project root for path validation
PROJECT_ROOT = Path(__file__).parent.resolve()

# Maximum tool calls per question (minimized for efficiency)
MAX_TOOL_CALLS = 3


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


def query_api(
    method: str,
    path: str,
    body: str | None = None,
    settings: Settings | None = None,
    auth: bool = True,
) -> str:
    """Call the backend LMS API and return the response.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: API endpoint path (e.g., /items/)
        body: Optional JSON request body for POST/PUT requests
        settings: Optional settings object with LMS API key
        auth: Whether to include authentication header (default: True)

    Returns:
        JSON string with status_code and body, or an error message
    """
    # Load LMS API key from settings or environment
    lms_api_key = (
        settings.lms_api_key if settings else os.environ.get("LMS_API_KEY", "")
    )
    api_base_url = (
        settings.agent_api_base_url
        if settings
        else os.environ.get("AGENT_API_BASE_URL", "http://localhost:42002")
    )

    # Build the URL
    url = f"{api_base_url}{path}"

    # Use Bearer token authentication (FastAPI HTTPBearer)
    headers = {
        "Content-Type": "application/json",
    }

    if auth:
        if not lms_api_key:
            return "Error: LMS_API_KEY not set in environment"
        headers["Authorization"] = f"Bearer {lms_api_key}"

    print(f"Calling API: {method} {url} (auth={auth})", file=sys.stderr)

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
                    "auth": {
                        "type": "boolean",
                        "description": "Whether to include authentication header (default: true). Set to false to test unauthenticated access.",
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
SYSTEM_PROMPT = """You are a helpful assistant that answers questions efficiently.

You have access to three tools:
- list_files: List files in a directory
- read_file: Read the contents of a file
- query_api: Call the backend API to query data or test endpoints

Tool selection (use minimum calls):
- Wiki/documentation questions → read_file on wiki/filename.md
- Source code questions → read_file on specific file path
- Data questions ("how many", counts) → query_api GET /endpoint
- API status codes/errors → query_api (check status_code)
- Bug diagnosis → query_api to see error, then read_file on source to find bug

For bug detection in code:
- Look for None-unsafe operations: sorted(None), len(None), None.attribute
- Check for missing null checks before operations
- Look for division without zero checks
- Identify TypeError risks from missing validation

Rules:
1. Answer in 1-2 sentences maximum
2. Include source reference (file path or API endpoint)
3. For bugs: state the error AND the buggy line location
4. Always provide an answer field - never return empty

Be direct. Use 1-2 tool calls maximum."""


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


def execute_tool_call(tool_call: dict, settings: Settings | None = None) -> dict:
    """Execute a single tool call and return the result.

    Args:
        tool_call: Dict with 'function' containing 'name' and 'arguments'
        settings: Optional settings object for tools that need it

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
        # Pass settings to query_api
        if tool_name == "query_api":
            result = TOOL_FUNCTIONS[tool_name](**args, settings=settings)
        else:
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
    last_answer = ""
    last_source = ""

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
            # Return fallback answer on error
            return f"Error: Could not process question. {question}", "", tool_calls

        # Check for tool calls - handle null content properly
        tool_calls_in_response = assistant_message.get("tool_calls") or []
        content = assistant_message.get("content")
        if content:
            last_answer = content
            last_source = extract_source_from_answer(content)

        if not tool_calls_in_response:
            # No tool calls - this is the final answer
            print("LLM returned final answer (no tool calls)", file=sys.stderr)
            if last_answer:
                return last_answer, last_source, tool_calls
            # Fallback: generate answer from context
            return "Question processed. Check tool results for details.", "", tool_calls

        # Execute each tool call
        for tool_call in tool_calls_in_response:
            result = execute_tool_call(tool_call, settings)
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

    # Max iterations reached - return best available answer
    print(f"Warning: Reached maximum tool calls ({MAX_TOOL_CALLS})", file=sys.stderr)

    if last_answer:
        return last_answer, last_source, tool_calls

    # Fallback: summarize tool results
    if tool_calls:
        summary = f"Processed with {len(tool_calls)} tool call(s). "
        for tc in tool_calls[:1]:
            if tc.get("result"):
                result_preview = str(tc["result"])[:200]
                summary += f"Result: {result_preview}"
        return summary, "", tool_calls

    return "Unable to answer question with available tools.", "", tool_calls


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
