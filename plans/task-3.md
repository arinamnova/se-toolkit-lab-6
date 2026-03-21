# Task 3 Plan: The System Agent

## Overview

This task extends the Task 2 agent with a new `query_api` tool that can query the deployed backend LMS API. The agent will answer:
1. **Static system facts** - framework, ports, status codes (from reading source code)
2. **Data-dependent queries** - item count, scores, analytics (from querying the API)

## New Tool: `query_api`

### Purpose
Call the deployed backend API to retrieve data or test endpoints.

### Parameters
- `method` (string, required) - HTTP method (GET, POST, etc.)
- `path` (string, required) - API endpoint path (e.g., `/items/`)
- `body` (string, optional) - JSON request body for POST/PUT requests

### Returns
JSON string with:
- `status_code`: HTTP status code
- `body`: Response body as JSON/string

### Authentication
- Uses `LMS_API_KEY` from `.env.docker.secret`
- Sent as `X-API-Key` header in the request

### Function Signature
```python
def query_api(method: str, path: str, body: str | None = None) -> str:
    """Call the backend API and return the response."""
```

### Tool Schema for LLM
```json
{
  "type": "function",
  "function": {
    "name": "query_api",
    "description": "Call the backend LMS API to query data or test endpoints. Use for questions about database contents, API behavior, or status codes.",
    "parameters": {
      "type": "object",
      "properties": {
        "method": {
          "type": "string",
          "description": "HTTP method (GET, POST, etc.)"
        },
        "path": {
          "type": "string",
          "description": "API endpoint path (e.g., /items/)"
        },
        "body": {
          "type": "string",
          "description": "JSON request body (optional, for POST/PUT)"
        }
      },
      "required": ["method", "path"]
    }
  }
}
```

## Environment Variables

The agent needs to read additional environment variables:

| Variable | Purpose | Source | Default |
|----------|---------|--------|---------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` | - |
| `LLM_API_BASE_URL` | LLM API endpoint URL | `.env.agent.secret` | - |
| `LLM_API_MODEL` | Model name | `.env.agent.secret` | `coder-model` |
| `LMS_API_KEY` | Backend API key for `query_api` auth | `.env.docker.secret` | - |
| `AGENT_API_BASE_URL` | Base URL for `query_api` | `.env.docker.secret` or env | `http://localhost:42002` |

### Settings Class Update
```python
class Settings(BaseSettings):
    """Load settings from .env.agent.secret and .env.docker.secret."""
    
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
```

**Note:** The autochecker injects its own credentials at runtime. We must read all config from environment variables, never hardcode.

## Updated System Prompt

The system prompt needs to guide the LLM on when to use which tool:

```
You are a helpful assistant that answers questions using:
1. The project wiki (for documentation)
2. The source code (for implementation details)
3. The backend API (for live data)

You have access to three tools:
- list_files: List files in a directory
- read_file: Read the contents of a file
- query_api: Call the backend API to query data or test endpoints

Tool selection guide:
- For wiki/documentation questions → use list_files and read_file on wiki/
- For source code questions → use list_files and read_file on backend/, agent.py, etc.
- For data questions (counts, scores, records) → use query_api
- For API behavior questions (status codes, errors) → use query_api

When using query_api:
- Use GET for retrieving data
- Use POST for creating data
- Always include the X-API-Key header (handled automatically)
- Check the status_code in the response

Always provide a source reference when applicable:
- Wiki files: wiki/filename.md#section
- Source files: path/to/file.py:function_name
- API responses: API endpoint path (e.g., GET /items/)
```

## Agentic Loop Changes

The agentic loop structure remains the same. We just:
1. Add `query_api` to the TOOLS list
2. Add `query_api` to the TOOL_FUNCTIONS mapping
3. The loop automatically handles the new tool

## Implementation Steps

1. **Update Settings class** to read `LMS_API_KEY` and `AGENT_API_BASE_URL`
2. **Implement `query_api` function** with proper authentication
3. **Add `query_api` to TOOLS** schema
4. **Update SYSTEM_PROMPT** to guide tool selection
5. **Update output format** - `source` is now optional (system questions may not have wiki source)
6. **Test with run_eval.py** and iterate until all 10 questions pass

## Testing Strategy

### Local Tests (run_eval.py)
The 10 questions cover:
- 0-1: Wiki lookup (read_file)
- 2-3: Source code reading (read_file, list_files)
- 4-7: API queries (query_api, sometimes with read_file for debugging)
- 8-9: Complex reasoning (LLM judge, read_file)

### Regression Tests (tests/test_agent.py)
Add 2 new tests:
1. `"What framework does the backend use?"` → expects `read_file` in tool_calls
2. `"How many items are in the database?"` → expects `query_api` in tool_calls

## Error Handling

- **Missing LMS_API_KEY**: Return error message from tool, don't crash
- **API connection error**: Return error message, continue loop
- **HTTP error (4xx, 5xx)**: Return status_code and error body as result
- **Invalid JSON body**: Return raw response text

## Benchmark Iteration Strategy

1. Run `uv run run_eval.py`
2. On first failure:
   - Read the feedback hint
   - Check which tool was used (or not used)
   - Adjust system prompt or tool description
   - Re-run
3. Repeat until all 10 pass

Common issues to watch for:
- Agent doesn't use a tool when it should → improve tool description
- Tool returns error → fix tool implementation
- Wrong arguments → clarify parameter descriptions
- Answer doesn't match keywords → adjust system prompt phrasing

## Acceptance Criteria Checklist

- [ ] `plans/task-3.md` exists with implementation plan and benchmark diagnosis
- [ ] `agent.py` defines `query_api` as function-calling schema
- [ ] `query_api` authenticates with `LMS_API_KEY` from environment
- [ ] Agent reads all LLM config from environment variables
- [ ] Agent reads `AGENT_API_BASE_URL` (defaults to `http://localhost:42002`)
- [ ] Agent answers static system questions correctly
- [ ] Agent answers data-dependent questions with plausible values
- [ ] `run_eval.py` passes all 10 local questions
- [ ] `AGENT.md` documents final architecture and lessons learned (200+ words)
- [ ] 2 tool-calling regression tests exist and pass
- [ ] Agent passes autochecker bot benchmark
- [ ] Git workflow: issue, branch, PR with `Closes #...`, partner approval, merge
