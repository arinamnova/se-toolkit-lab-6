"""Regression tests for agent.py.

Tests verify that the agent:
1. Produces valid JSON output
2. Includes required fields (answer, tool_calls)
3. Handles questions correctly
"""

import json
import subprocess
import sys
from pathlib import Path


def test_agent_output_structure():
    """Test that agent.py outputs valid JSON with required fields.

    This test runs agent.py with a simple question and verifies:
    - The output is valid JSON
    - The 'answer' field exists and is non-empty
    - The 'tool_calls' field exists and is a list
    """
    # Run agent.py with a test question
    result = subprocess.run(
        [sys.executable, "agent.py", "What is 2 + 2?"],
        capture_output=True,
        text=True,
        timeout=60,
    )

    # Check exit code
    assert result.returncode == 0, (
        f"Agent exited with code {result.returncode}: {result.stderr}"
    )

    # Check stdout is not empty
    assert result.stdout.strip(), "Agent produced no output"

    # Parse JSON
    try:
        data = json.loads(result.stdout.strip())
    except json.JSONDecodeError as e:
        raise AssertionError(
            f"Agent output is not valid JSON: {result.stdout[:200]}"
        ) from e

    # Check required fields
    assert "answer" in data, "Missing 'answer' field in output"
    assert data["answer"], "'answer' field is empty"
    assert isinstance(data["answer"], str), "'answer' field is not a string"

    assert "tool_calls" in data, "Missing 'tool_calls' field in output"
    assert isinstance(data["tool_calls"], list), "'tool_calls' field is not a list"


def test_agent_no_question():
    """Test that agent.py exits with error when no question is provided."""
    result = subprocess.run(
        [sys.executable, "agent.py"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    # Should exit with non-zero code
    assert result.returncode != 0, (
        "Agent should exit with non-zero code when no question provided"
    )

    # Should print usage to stderr
    assert "Usage" in result.stderr or "usage" in result.stderr, (
        "Agent should print usage to stderr"
    )


def test_agent_read_file_tool():
    """Test that agent.py uses read_file tool for wiki questions.

    This test runs agent.py with a question about resolving merge conflicts
    and verifies:
    - The output contains tool_calls
    - At least one tool_call uses 'read_file'
    - The source field references a wiki file (git-vscode.md or git-workflow.md)
    """
    # Run agent.py with a question that requires reading wiki files
    result = subprocess.run(
        [sys.executable, "agent.py", "How do you resolve a merge conflict?"],
        capture_output=True,
        text=True,
        timeout=120,
    )

    # Check exit code
    assert result.returncode == 0, (
        f"Agent exited with code {result.returncode}: {result.stderr}"
    )

    # Parse JSON
    try:
        data = json.loads(result.stdout.strip())
    except json.JSONDecodeError as e:
        raise AssertionError(
            f"Agent output is not valid JSON: {result.stdout[:200]}"
        ) from e

    # Check tool_calls is not empty
    assert len(data["tool_calls"]) > 0, (
        "Expected tool_calls to be non-empty for wiki question"
    )

    # Check that read_file was used
    tool_names = [call.get("tool") for call in data["tool_calls"]]
    assert "read_file" in tool_names, (
        f"Expected 'read_file' in tool_calls, got: {tool_names}"
    )

    # Check source field references a git-related wiki file
    assert "source" in data, "Missing 'source' field in output"
    source = data["source"]
    assert source, "'source' field is empty"
    # Source should reference git-vscode.md or git-workflow.md
    assert "git" in source.lower() and ".md" in source, (
        f"Source '{source}' should reference a git-related wiki file"
    )


def test_agent_list_files_tool():
    """Test that agent.py uses list_files tool for directory questions.

    This test runs agent.py with a question about wiki files
    and verifies:
    - The output contains tool_calls
    - At least one tool_call uses 'list_files'
    - The answer mentions wiki files
    """
    # Run agent.py with a question that requires listing directory
    result = subprocess.run(
        [sys.executable, "agent.py", "What files are in the wiki?"],
        capture_output=True,
        text=True,
        timeout=120,
    )

    # Check exit code
    assert result.returncode == 0, (
        f"Agent exited with code {result.returncode}: {result.stderr}"
    )

    # Parse JSON
    try:
        data = json.loads(result.stdout.strip())
    except json.JSONDecodeError as e:
        raise AssertionError(
            f"Agent output is not valid JSON: {result.stdout[:200]}"
        ) from e

    # Check tool_calls is not empty
    assert len(data["tool_calls"]) > 0, (
        "Expected tool_calls to be non-empty for directory question"
    )

    # Check that list_files was used
    tool_names = [call.get("tool") for call in data["tool_calls"]]
    assert "list_files" in tool_names, (
        f"Expected 'list_files' in tool_calls, got: {tool_names}"
    )

    # Check answer exists
    assert "answer" in data, "Missing 'answer' field in output"
    assert data["answer"], "'answer' field is empty"
