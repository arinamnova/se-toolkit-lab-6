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
    assert result.returncode == 0, f"Agent exited with code {result.returncode}: {result.stderr}"

    # Check stdout is not empty
    assert result.stdout.strip(), "Agent produced no output"

    # Parse JSON
    try:
        data = json.loads(result.stdout.strip())
    except json.JSONDecodeError as e:
        raise AssertionError(f"Agent output is not valid JSON: {result.stdout[:200]}") from e

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
    assert result.returncode != 0, "Agent should exit with non-zero code when no question provided"

    # Should print usage to stderr
    assert "Usage" in result.stderr or "usage" in result.stderr, "Agent should print usage to stderr"
