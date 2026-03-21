# Agent Architecture

## Overview

This is a CLI-based agent that connects to an LLM (Large Language Model) API and returns structured JSON responses. It serves as the foundation for a more advanced agentic system that will be built in subsequent tasks.

## LLM Provider

**Provider:** Qwen Code API

**Model:** `coder-model` (Qwen 3.5 Plus)

**Why this provider:**
- OpenAI-compatible API (easy integration)
- 1000 free requests per day
- Works from Russia without restrictions
- No credit card required

## Architecture

### Data Flow

```
User Input (CLI arg) → agent.py → LLM API → JSON Output (stdout)
```

1. User provides a question as a command-line argument
2. `agent.py` reads environment variables from `.env.agent.secret`
3. `agent.py` makes an HTTP POST request to the LLM's `/chat/completions` endpoint
4. The LLM processes the question and returns a response
5. `agent.py` extracts the answer and outputs JSON to stdout

### Components

#### `agent.py`

The main CLI entry point with the following responsibilities:

- **Argument Parsing:** Reads the question from `sys.argv[1]`
- **Settings Loading:** Uses `pydantic-settings` to load API credentials from `.env.agent.secret`
- **LLM Client:** Uses `httpx` to make async HTTP requests to the LLM API
- **Response Parsing:** Extracts the answer from the LLM response structure
- **Output Formatting:** Outputs valid JSON with `answer` and `tool_calls` fields

### Environment Variables

The agent reads from `.env.agent.secret`:

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_API_KEY` | API key for authentication | `sk-...` |
| `LLM_API_BASE_URL` | Base URL of the LLM API | `http://vm-ip:8080/v1` |
| `LLM_API_MODEL` | Model name to use | `coder-model` |

### Output Format

The agent outputs a single JSON line to stdout:

```json
{
  "answer": "The LLM's response text",
  "tool_calls": []
}
```

- `answer`: The text response from the LLM
- `tool_calls`: Empty array (will be populated in Task 2 when tools are added)

### Error Handling

- **Missing question:** Exits with code 1, prints usage to stderr
- **Settings error:** Exits with code 1, prints error to stderr
- **API timeout:** Exits with code 1 after 60 seconds
- **Connection error:** Exits with code 1, prints error to stderr
- **Invalid response:** Exits with code 1, prints error to stderr

All debug/error output goes to **stderr**, keeping stdout clean for JSON output.

## Usage

### Basic Usage

```bash
uv run agent.py "What is the capital of France?"
```

### Expected Output

```json
{"answer": "The capital of France is Paris.", "tool_calls": []}
```

### Testing

Run the regression test:

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
├── agent.py              # Main CLI entry point
├── .env.agent.secret     # LLM credentials (gitignored)
├── AGENT.md              # This documentation
├── plans/
│   └── task-1.md         # Implementation plan
└── tests/
    └── test_agent.py     # Regression test
```

## Future Work (Tasks 2-3)

In the next tasks, the agent will be extended with:

- **Tools:** Ability to call external tools (file read, API queries, etc.)
- **Agentic Loop:** Multi-step reasoning with tool usage
- **Domain Knowledge:** Integration with the backend LMS
