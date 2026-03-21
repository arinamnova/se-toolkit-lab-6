# Task 2 Plan: The Documentation Agent

## Overview

This task extends the Task 1 CLI agent with **tools** and an **agentic loop**. The agent will be able to:
1. Use `read_file` to read files from the project repository
2. Use `list_files` to list directory contents
3. Execute a multi-step loop: call LLM → execute tools → feed results back → get final answer

## Tool Schemas

### `read_file`

**Purpose:** Read a file from the project repository.

**Parameters:**
- `path` (string, required): Relative path from project root

**Returns:** File contents as a string, or an error message if the file doesn't exist.

**Security:**
- Must not read files outside the project directory (no `../` traversal)
- Validate that the resolved path is within the project root

**Function signature:**
```python
def read_file(path: str) -> str:
    """Read a file from the project repository."""
```

### `list_files`

**Purpose:** List files and directories at a given path.

**Parameters:**
- `path` (string, required): Relative directory path from project root

**Returns:** Newline-separated listing of entries.

**Security:**
- Must not list directories outside the project directory
- Validate that the resolved path is within the project root

**Function signature:**
```python
def list_files(path: str) -> str:
    """List files and directories at a given path."""
```

## Tool Schema for LLM

The tools will be registered as function-calling schemas in the LLM request. Using OpenAI-compatible format:

```python
tools = [
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
                        "description": "Relative directory path from project root"
                    }
                },
                "required": ["path"]
            }
        }
    }
]
```

## Agentic Loop

The agentic loop will:
1. Send the user's question + tool definitions to the LLM
2. If the LLM responds with `tool_calls`:
   - Execute each tool call
   - Append results as `tool` role messages
   - Send back to LLM and repeat
3. If the LLM responds with a text message (no tool calls):
   - Extract the answer and source
   - Output JSON and exit
4. Maximum 10 tool calls per question (safety limit)

### Message Flow

```
User question → LLM (with tools) → tool_calls
                                    ↓
execute tools ← LLM response
                                    ↓
append tool results as messages
                                    ↓
send back to LLM → repeat (max 10 iterations)
                                    ↓
LLM returns final answer (no tool calls)
                                    ↓
output JSON: {answer, source, tool_calls}
```

### System Prompt Strategy

The system prompt will instruct the LLM to:
1. Use `list_files` to discover wiki files when needed
2. Use `read_file` to read specific wiki files and find answers
3. Include the source reference (file path + section anchor) in the final answer
4. Only make tool calls when necessary to answer the question

Example system prompt:
```
You are a helpful assistant that answers questions using the project wiki.
You have access to two tools:
- list_files: List files in a directory
- read_file: Read the contents of a file

To answer a question:
1. First use list_files to explore the wiki directory structure if needed
2. Use read_file to read relevant wiki files
3. Find the answer in the file contents
4. Provide the answer with a source reference (file path and section anchor)

Always include the source field in your final answer.
```

## Path Security

To prevent directory traversal attacks:
1. Resolve all paths relative to the project root
2. Check that the resolved absolute path is within the project directory
3. Reject any path that contains `..` or resolves outside the project

Implementation:
```python
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()

def validate_path(relative_path: str) -> Path:
    """Validate and resolve a relative path within the project."""
    # Reject paths with ..
    if ".." in relative_path:
        raise ValueError(f"Path traversal not allowed: {relative_path}")
    
    # Resolve the full path
    full_path = (PROJECT_ROOT / relative_path).resolve()
    
    # Check it's within project root
    if not str(full_path).startswith(str(PROJECT_ROOT)):
        raise ValueError(f"Path outside project directory: {relative_path}")
    
    return full_path
```

## Output Format

The output JSON will include:
- `answer`: The LLM's final answer text
- `source`: The wiki section reference (e.g., `wiki/git-vscode.md#resolve-a-merge-conflict`)
- `tool_calls`: Array of all tool calls made, each with `tool`, `args`, and `result`

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

## Error Handling

- **File not found:** Return error message as tool result, continue loop
- **Path traversal attempt:** Return error message, do not access file
- **LLM returns invalid tool call:** Return error message as tool result
- **Max iterations reached:** Stop loop, return best available answer
- **API errors:** Exit with code 1, print error to stderr

## Testing Strategy

Two regression tests:

1. **Test `read_file` usage:**
   - Question: `"How do you resolve a merge conflict?"`
   - Expected: `read_file` in tool_calls, `wiki/git-vscode.md` in source

2. **Test `list_files` usage:**
   - Question: `"What files are in the wiki?"`
   - Expected: `list_files` in tool_calls

Tests will:
- Run `agent.py` as a subprocess
- Parse JSON output
- Verify tool_calls contain expected tools
- Verify source field contains expected file path

## File Structure

```
se-toolkit-lab-6/
├── agent.py              # Updated with tools and agentic loop
├── AGENT.md              # Updated documentation
├── plans/
│   └── task-2.md         # This plan
└── tests/
    └── test_agent.py     # Updated with 2 more tests
```

## Dependencies

No new dependencies needed. Using:
- `httpx` - HTTP client
- `pydantic-settings` - Environment variable loading
- `pathlib` - Path handling (standard library)
- `json`, `sys` - Standard library

## Acceptance Criteria Checklist

- [ ] `plans/task-2.md` exists with the implementation plan (committed before code)
- [ ] `agent.py` defines `read_file` and `list_files` as tool schemas
- [ ] The agentic loop executes tool calls and feeds results back to the LLM
- [ ] `tool_calls` in the output is populated when tools are used
- [ ] The `source` field correctly identifies the wiki section that answers the question
- [ ] Tools do not access files outside the project directory
- [ ] `AGENT.md` documents the tools and agentic loop
- [ ] 2 tool-calling regression tests exist and pass
- [ ] Git workflow: issue `[Task] The Documentation Agent`, branch, PR with `Closes #...`, partner approval, merge
