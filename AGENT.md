# Agent Architecture

## Overview

This is a CLI-based agent with **tools** and an **agentic loop** that connects to an LLM API and returns structured JSON responses. The agent can:

1. Read files and list directories from the project wiki and source code
2. Query the deployed backend LMS API for live data
3. Execute multi-step reasoning loops to answer complex questions

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
                                         Execute tools (read_file, list_files, query_api)
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
                         ↑                        ↓
                         └────────────────────────┘
                                  (loop)
```

### Components

#### `agent.py`

The main CLI entry point with the following components:

**1. Settings Loader**

- Uses `pydantic-settings` to load API credentials from `.env.agent.secret` and `.env.docker.secret`
- Validates required environment variables
- Supports environment variable injection for autochecker compatibility

**2. Tool Functions**

- `read_file(path)`: Read a file from the project repository
- `list_files(path)`: List files and directories at a given path
- `query_api(method, path, body)`: Call the backend LMS API with authentication

**3. Path Security**

- `validate_path(relative_path)`: Ensures paths stay within project root
- Rejects any path containing `..`
- Verifies resolved absolute path starts with project root

**4. LLM Client**

- Uses `httpx` for HTTP requests to the LLM API
- Supports function calling with tool definitions
- Handles timeouts (60 seconds) and API errors gracefully

**5. API Client**

- Uses `httpx` for HTTP requests to the backend LMS API
- Authenticates with `X-API-Key` header using `LMS_API_KEY`
- Handles GET, POST, PUT, DELETE methods
- Parses JSON responses automatically

**6. Agentic Loop**

- `run_agentic_loop(question, settings)`: Main loop that orchestrates tool usage
- Tracks all tool calls for output
- Extracts source references from the final answer

**7. Response Parser**

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
    "description": "Read a file from the project repository. Use for wiki documentation or source code questions.",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "description": "Relative path from project root (e.g., wiki/git.md or backend/app/main.py)"
        }
      },
      "required": ["path"]
    }
  }
}
```

### System Prompt Strategy

The system prompt instructs the LLM to:

1. Use `list_files` to discover wiki files or source code structure when needed
2. Use `read_file` to read specific wiki files or source code
3. Use `query_api` for data questions (counts, scores) and API behavior questions (status codes, errors)
4. Include the source reference (file path + section anchor or API endpoint) in the final answer
5. Only make tool calls when necessary to answer the question

**Tool Selection Guide (from system prompt):**

- For wiki/documentation questions (git, docker, ssh, etc.) → use `list_files` and `read_file` on `wiki/`
- For source code questions (framework, architecture, code structure) → use `list_files` and `read_file` on `backend/`, `agent.py`, `docker-compose.yml`, etc.
- For data questions (counts, scores, records, "how many") → use `query_api` with GET
- For API behavior questions (status codes, errors, authentication) → use `query_api`

## Environment Variables

The agent reads from multiple environment files for separation of concerns:

| Variable | Purpose | Source | Default |
|----------|---------|--------|---------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` | - |
| `LLM_API_BASE_URL` | LLM API endpoint URL | `.env.agent.secret` | - |
| `LLM_API_MODEL` | Model name | `.env.agent.secret` | `coder-model` |
| `LMS_API_KEY` | Backend API key for `query_api` auth | `.env.docker.secret` | - |
| `AGENT_API_BASE_URL` | Base URL for `query_api` | `.env.docker.secret` or env | `http://localhost:42002` |

**Important:** The autochecker injects its own credentials at runtime. All configuration is read from environment variables, never hardcoded.

## Output Format

The agent outputs a single JSON line to stdout:

```json
{
  "answer": "There are 120 items in the database.",
  "source": "GET /items/",
  "tool_calls": [
    {"tool": "query_api", "args": {"method": "GET", "path": "/items/"}, "result": "{\"status_code\": 200, \"body\": {...}}"}
  ]
}
```

- `answer`: The LLM's final answer text
- `source`: The source reference (wiki file, source file, or API endpoint)
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
- **Missing LMS_API_KEY:** Returns error message from `query_api` tool
- **API connection error:** Returns error message, continues loop

All debug/error output goes to **stderr**, keeping stdout clean for JSON output.

## Usage

### Basic Usage

```bash
uv run agent.py "How do you resolve a merge conflict?"
uv run agent.py "How many items are in the database?"
uv run agent.py "What HTTP status code does /items/ return without auth?"
```

### Expected Output (Wiki Question)

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

### Expected Output (API Question)

```json
{
  "answer": "There are 120 items in the database.",
  "source": "GET /items/",
  "tool_calls": [
    {"tool": "query_api", "args": {"method": "GET", "path": "/items/"}, "result": "{\"status_code\": 200, \"body\": [...]}"}
  ]
}
```

### Testing

Run the regression tests:

```bash
uv run pytest tests/test_agent.py
```

Run the evaluation benchmark:

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
├── .env.docker.secret    # Backend API credentials (gitignored)
├── .env                  # Autochecker credentials (gitignored)
├── AGENT.md              # This documentation
├── plans/
│   ├── task-1.md         # Implementation plan for Task 1
│   ├── task-2.md         # Implementation plan for Task 2
│   └── task-3.md         # Implementation plan for Task 3
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

### API Authentication

The `query_api` tool authenticates with the backend using:

- `X-API-Key` header with `LMS_API_KEY` from environment
- Never hardcodes credentials in source code
- Reads from `.env.docker.secret` (gitignored)

## Lessons Learned

### Tool Description Design

The initial tool descriptions were too vague, causing the LLM to use the wrong tool for certain questions. After iteration:

- **`read_file`**: Explicitly mention "wiki documentation or source code questions"
- **`list_files`**: Emphasize "explore directory structure"
- **`query_api`**: Clearly state "NOT for wiki or source code questions" and give examples of when to use it

### System Prompt Iteration

The system prompt went through several iterations:

1. **Initial:** Only mentioned wiki files → LLM never used `query_api`
2. **Second:** Added source code reading → LLM used `read_file` for everything
3. **Third:** Added explicit tool selection guide with examples → LLM correctly chooses tools
4. **Final:** Added specific guidance for complex questions (explore first, then read, then query)

### Handling Null Content

When the LLM returns tool calls, the `content` field is `null` (not missing). Using `msg.get("content", "")` returns `None` instead of `""`. Fixed by using `(msg.get("content") or "")`.

### API Error Handling

The `query_api` tool needed robust error handling:

- Connection errors → return descriptive message
- Timeout → return timeout message
- HTTP errors (4xx, 5xx) → return status code and body
- Invalid JSON body → return raw text

This allows the LLM to reason about errors and potentially diagnose bugs.

## Final Evaluation Score

**Note:** The evaluation requires a running backend. See `plans/task-3.md` for instructions on starting the backend and running the evaluation.

**Expected Results:**

- Questions 0-1: Wiki lookup → `read_file` on `wiki/`
- Questions 2-3: Source code reading → `read_file`/`list_files` on `backend/`
- Questions 4-7: API queries → `query_api` with GET
- Questions 8-9: Complex reasoning → `read_file` with LLM judge

## Future Work

Potential extensions:

- **Caching:** Cache API responses to reduce redundant calls
- **Retry logic:** Retry failed API calls with exponential backoff
- **More tools:** Add tools for database queries, file search, code execution
- **Streaming:** Stream LLM responses for faster feedback
- **Conversation history:** Support multi-turn conversations
