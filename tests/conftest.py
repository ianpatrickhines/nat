"""
Root test configuration and fixtures.

Mocks the claude_agent_sdk module for testing since it may not be publicly available.
"""

import sys
from typing import Any
from unittest.mock import MagicMock


def tool(name: str, description: str, schema: dict[str, Any]) -> Any:
    """Mock @tool decorator that just returns the function as-is."""
    def decorator(func: Any) -> Any:
        func._tool_name = name
        func._tool_description = description
        func._tool_schema = schema
        return func
    return decorator


# Create a mock claude_agent_sdk module if it doesn't exist
if "claude_agent_sdk" not in sys.modules:
    mock_sdk = MagicMock()
    mock_sdk.tool = tool
    sys.modules["claude_agent_sdk"] = mock_sdk
