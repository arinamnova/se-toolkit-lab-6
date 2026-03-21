# Task 1 Plan: Call an LLM from Code

## LLM Provider

**Provider:** Qwen Code API (deployed on VM)

**Model:** `coder-model` (Qwen 3.5 Plus)

**Why this choice:**
- 1000 free requests per day
- Works from Russia
- No credit card required
- OpenAI-compatible API (easy to integrate)

## Architecture

### Data Flow

1. User runs `uv run agent.py "question"`
2. `agent.py` reads the question from `sys.argv[1]`
3. `agent.py` loads environment variables from `.env.agent.secret`
4. `agent.py` makes an HTTP POST request to the LLM API
5. LLM returns a response
6. `agent.py` parses the response and outputs JSON to stdout

### Components

1. **Environment Loader**
   - Read `LLM_API_KEY`, `LLM_API_BASE_URL`, `LLM_API_MODEL` from `.env.agent.secret`
   - Use `pydantic-settings` (already in project dependencies)

2. **LLM Client**
   - Use `httpx` (already in project dependencies) for async HTTP requests
   - Call the OpenAI-compatible `/chat/completions` endpoint
   - Send the user's question as a message

3. **Response Parser**
   - Extract the answer from the LLM response
   - Format output as JSON: `{"answer": "...", "tool_calls": []}`

4. **CLI Entry Point**
   - Parse command-line arguments
   - Orchestrate the flow
   - Output JSON to stdout, errors to stderr

## Error Handling

- **Missing question:** Exit with code 1, print usage to stderr
- **API error:** Exit with code 1, print error to stderr
- **Timeout:** The API call should complete within 60 seconds
- **Invalid response:** Exit with code 1, print error to stderr

## Testing Strategy

**Test:** `tests/test_agent.py`

- Run `agent.py` as a subprocess with a test question
- Parse stdout as JSON
- Verify `answer` field exists and is non-empty
- Verify `tool_calls` field exists (will be empty array for Task 1)

## File Structure

```
se-toolkit-lab-6/
├── agent.py              # Main CLI entry point
├── .env.agent.secret     # LLM credentials (gitignored)
├── AGENT.md              # Documentation
├── plans/
│   └── task-1.md         # This plan
└── tests/
    └── test_agent.py     # Regression test
```

## Dependencies

No new dependencies needed. Using:
- `httpx` - HTTP client
- `pydantic-settings` - Environment variable loading
- `sys`, `json` - Standard library

## Acceptance Criteria Checklist

- [ ] Plan created before code
- [ ] `agent.py` outputs valid JSON with `answer` and `tool_calls`
- [ ] API key in `.env.agent.secret` (not hardcoded)
- [ ] Debug output to stderr
- [ ] Exit code 0 on success
- [ ] 1 regression test passes
