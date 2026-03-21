# Agent Architecture

## Overview

This is a CLI-based agent with **tools** and an **agentic loop** that connects to an LLM API and returns structured JSON responses. The agent can read files and list directories from the project wiki to answer questions with proper source references.

## LLM Provider

**Provider:** Qwen Code API

**Model:** `coder-model` (Qwen 3.5 Plus)

**Why this provider:**

- OpenAI-compatible API (easy integration)
- 1000 free requests per day
- Works from Russia without restrictions
- No credit card required

## Architecture

### Agentic Loop

The agent implements a multi-step reasoning loop:

```
User Input (CLI arg) → Send to LLM with tools → LLM returns tool_calls
                                                        ↓
                                         Execute tools (read_file, list_files)
                                                        ↓
                                         Append results as tool messages
                                                        ↓
                                         Send back to LLM (repeat)
                                                        ↓
                                         LLM returns final answer
                                                        ↓
                                         Output JSON (answer, source, tool_calls)
```

1. Send the user's question + tool definitions to the LLM
2. If the LLM responds with `tool_calls`:
   - Execute each tool call
   - Append results as `tool` role messages
   - Send back to LLM and repeat
3. If the LLM responds with a text message (no tool calls):
   - Extract the answer and source
   - Output JSON and exit
4. Maximum 10 tool calls per question (safety limit)

### Data Flow

```
User Input → agent.py → LLM API (with tools) → Tool Execution → LLM API → JSON Output
```

### Components

#### `agent.py`

The main CLI entry point with the following components:

**1. Settings Loader**

- Uses `pydantic-settings` to load API credentials from `.env.agent.secret`
- Validates required environment variables

**2. Tool Functions**

- `read_file(path)`: Read a file from the project repository
- `list_files(path)`: List files and directories at a given path
- Both tools validate paths to prevent directory traversal attacks

**3. Path Security**

- `validate_path(relative_path)`: Ensures paths stay within project root
- Rejects any path containing `..`
- Verifies resolved absolute path starts with project root

**4. LLM Client**

- Uses `httpx` for HTTP requests to the LLM API
- Supports function calling with tool definitions
- Handles timeouts (60 seconds) and API errors gracefully

**5. Agentic Loop**

- `run_agentic_loop(question, settings)`: Main loop that orchestrates tool usage
- Tracks all tool calls for output
- Extracts source references from the final answer

**6. Response Parser**

- Extracts the answer from the LLM response
- Parses tool calls and their results
- Outputs valid JSON with `answer`, `source`, and `tool_calls` fields

### Tool Schemas

Tools are registered as function-calling schemas in OpenAI-compatible format:

```json
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
          "description": "Relative path from project root"
        }
      },
      "required": ["path"]
    }
  }
}
```

### System Prompt Strategy

The system prompt instructs the LLM to:

1. Use `list_files` to discover wiki files when needed
2. Use `read_file` to read specific wiki files and find answers
3. Include the source reference (file path + section anchor) in the final answer
4. Only make tool calls when necessary to answer the question

## Environment Variables

The agent reads from `.env.agent.secret`:

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_API_KEY` | API key for authentication | `sk-...` |
| `LLM_API_BASE_URL` | Base URL of the LLM API | `http://vm-ip:8080/v1` |
| `LLM_API_MODEL` | Model name to use | `coder-model` |

## Output Format

The agent outputs a single JSON line to stdout:

```json
{
  "answer": "Edit the conflicting file, choose which changes to keep, then stage and commit.",
  "source": "wiki/git-vscode.md#resolve-a-merge-conflict",
  "tool_calls": [
    {"tool": "list_files", "args": {"path": "wiki"}, "result": "git-workflow.md\ngit-vscode.md\n..."},
    {"tool": "read_file", "args": {"path": "wiki/git-vscode.md"}, "result": "..."}
  ]
}
```

- `answer`: The LLM's final answer text
- `source`: The wiki section reference (e.g., `wiki/git-vscode.md#resolve-a-merge-conflict`)
- `tool_calls`: Array of all tool calls made, each with `tool`, `args`, and `result`

### Error Handling

- **Missing question:** Exits with code 1, prints usage to stderr
- **Settings error:** Exits with code 1, prints error to stderr
- **API timeout:** Exits with code 1 after 60 seconds
- **Connection error:** Exits with code 1, prints error to stderr
- **Invalid response:** Exits with code 1, prints error to stderr
- **File not found:** Returns error message as tool result, continues loop
- **Path traversal attempt:** Returns error message, does not access file
- **Max iterations reached:** Stops loop, returns best available answer

All debug/error output goes to **stderr**, keeping stdout clean for JSON output.

## Usage

### Basic Usage

```bash
uv run agent.py "How do you resolve a merge conflict?"
```

### Expected Output

```json
{
  "answer": "To resolve a merge conflict, open the conflicting file and look for conflict markers...",
  "source": "wiki/git-vscode.md#resolve-a-merge-conflict",
  "tool_calls": [
    {"tool": "list_files", "args": {"path": "wiki"}, "result": "..."},
    {"tool": "read_file", "args": {"path": "wiki/git-vscode.md"}, "result": "..."}
  ]
}
```

### Testing

Run the regression tests:

```bash
uv run pytest tests/test_agent.py
```

Run the evaluation script:

```bash
uv run run_eval.py
```

## Dependencies

The agent uses the following dependencies (already in `pyproject.toml`):

- `httpx>=0.28.1` - Async HTTP client for API calls
- `pydantic-settings>=2.12.0` - Environment variable loading and validation

## File Structure

```
se-toolkit-lab-6/
├── agent.py              # Main CLI entry point with tools and agentic loop
├── .env.agent.secret     # LLM credentials (gitignored)
├── AGENT.md              # This documentation
├── plans/
│   └── task-1.md         # Implementation plan for Task 1
│   └── task-2.md         # Implementation plan for Task 2
└── tests/
    └── test_agent.py     # Regression tests
```

## Security

### Path Validation

All file operations validate paths to prevent directory traversal:

1. Reject any path containing `..`
2. Resolve the full absolute path
3. Verify the resolved path starts with the project root
4. Return an error message if validation fails

This ensures the agent cannot read files outside the project directory.

## Future Work (Task 3)

In the next task, the agent will be extended with:

- **Backend Integration:** Query the LMS backend via `query_api` tool
- **Domain Knowledge:** Answer questions about courses, students, and grades
- **Multi-hop Reasoning:** Chain multiple API calls to answer complex questions
