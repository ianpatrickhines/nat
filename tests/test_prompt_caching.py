"""
Tests for prompt caching configuration in Nat agent.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.nat.agent import _setup_prompt_caching, create_nat_options


class TestPromptCaching:
    """Tests for prompt caching configuration."""

    def test_setup_prompt_caching_enables_beta_flag(self) -> None:
        """Test that prompt caching sets the ANTHROPIC_BETA environment variable."""
        # Clear any existing ANTHROPIC_BETA
        original_beta = os.environ.pop("ANTHROPIC_BETA", None)
        
        try:
            _setup_prompt_caching()
            
            # Should have set the beta flag
            assert "ANTHROPIC_BETA" in os.environ
            assert "prompt-caching-2024-07-31" in os.environ["ANTHROPIC_BETA"]
        finally:
            # Restore original value
            if original_beta:
                os.environ["ANTHROPIC_BETA"] = original_beta
            else:
                os.environ.pop("ANTHROPIC_BETA", None)

    def test_setup_prompt_caching_preserves_existing_beta(self) -> None:
        """Test that prompt caching preserves existing beta flags."""
        # Set an existing beta flag
        original_beta = os.environ.get("ANTHROPIC_BETA")
        os.environ["ANTHROPIC_BETA"] = "some-other-beta"
        
        try:
            _setup_prompt_caching()
            
            # Should have both beta flags
            assert "some-other-beta" in os.environ["ANTHROPIC_BETA"]
            assert "prompt-caching-2024-07-31" in os.environ["ANTHROPIC_BETA"]
        finally:
            # Restore original value
            if original_beta:
                os.environ["ANTHROPIC_BETA"] = original_beta
            else:
                os.environ.pop("ANTHROPIC_BETA", None)

    def test_setup_prompt_caching_respects_disable_flag(self) -> None:
        """Test that caching can be disabled via environment variable."""
        # Set the disable flag
        original_disable = os.environ.get("NAT_DISABLE_PROMPT_CACHING")
        original_beta = os.environ.get("ANTHROPIC_BETA")
        os.environ["NAT_DISABLE_PROMPT_CACHING"] = "true"
        os.environ.pop("ANTHROPIC_BETA", None)
        
        try:
            _setup_prompt_caching()
            
            # Should NOT have set the beta flag
            assert "ANTHROPIC_BETA" not in os.environ
        finally:
            # Restore original values
            if original_disable:
                os.environ["NAT_DISABLE_PROMPT_CACHING"] = original_disable
            else:
                os.environ.pop("NAT_DISABLE_PROMPT_CACHING", None)
            if original_beta:
                os.environ["ANTHROPIC_BETA"] = original_beta
            else:
                os.environ.pop("ANTHROPIC_BETA", None)

    def test_setup_prompt_caching_does_not_duplicate(self) -> None:
        """Test that calling setup multiple times doesn't duplicate the beta flag."""
        original_beta = os.environ.get("ANTHROPIC_BETA")
        os.environ.pop("ANTHROPIC_BETA", None)
        
        try:
            _setup_prompt_caching()
            first_value = os.environ["ANTHROPIC_BETA"]
            
            _setup_prompt_caching()
            second_value = os.environ["ANTHROPIC_BETA"]
            
            # Should be the same
            assert first_value == second_value
        finally:
            if original_beta:
                os.environ["ANTHROPIC_BETA"] = original_beta
            else:
                os.environ.pop("ANTHROPIC_BETA", None)

    @patch("src.nat.agent.ALL_TOOLS", [])
    @patch("src.nat.agent.init_client")
    @patch("src.nat.agent.create_sdk_mcp_server")
    def test_create_nat_options_enables_caching_by_default(
        self, mock_mcp_server: MagicMock, mock_init_client: MagicMock
    ) -> None:
        """Test that create_nat_options enables caching by default."""
        mock_mcp_server.return_value = MagicMock()
        
        original_beta = os.environ.get("ANTHROPIC_BETA")
        os.environ.pop("ANTHROPIC_BETA", None)
        
        try:
            create_nat_options("test_slug", "test_token")
            
            # Should have enabled caching
            assert "ANTHROPIC_BETA" in os.environ
            assert "prompt-caching-2024-07-31" in os.environ["ANTHROPIC_BETA"]
        finally:
            if original_beta:
                os.environ["ANTHROPIC_BETA"] = original_beta
            else:
                os.environ.pop("ANTHROPIC_BETA", None)

    @patch("src.nat.agent.ALL_TOOLS", [])
    @patch("src.nat.agent.init_client")
    @patch("src.nat.agent.create_sdk_mcp_server")
    def test_create_nat_options_can_disable_caching(
        self, mock_mcp_server: MagicMock, mock_init_client: MagicMock
    ) -> None:
        """Test that create_nat_options can disable caching."""
        mock_mcp_server.return_value = MagicMock()
        
        original_beta = os.environ.get("ANTHROPIC_BETA")
        os.environ.pop("ANTHROPIC_BETA", None)
        
        try:
            create_nat_options("test_slug", "test_token", enable_caching=False)
            
            # Should NOT have enabled caching
            assert "ANTHROPIC_BETA" not in os.environ
        finally:
            if original_beta:
                os.environ["ANTHROPIC_BETA"] = original_beta
            else:
                os.environ.pop("ANTHROPIC_BETA", None)

    @patch("src.nat.agent.ClaudeAgentOptions")
    @patch("src.nat.agent.ALL_TOOLS", [])
    @patch("src.nat.agent.init_client")
    @patch("src.nat.agent.create_sdk_mcp_server")
    def test_create_nat_options_returns_correct_model(
        self, mock_mcp_server: MagicMock, mock_init_client: MagicMock, mock_options_class: MagicMock
    ) -> None:
        """Test that create_nat_options returns correct model."""
        mock_mcp_server.return_value = MagicMock()
        
        # Mock ClaudeAgentOptions to capture the arguments
        mock_instance = MagicMock()
        mock_options_class.return_value = mock_instance
        
        original_beta = os.environ.get("ANTHROPIC_BETA")
        
        try:
            options = create_nat_options("test_slug", "test_token")
            
            # Check that ClaudeAgentOptions was called with default model
            assert mock_options_class.call_args.kwargs["model"] == "claude-haiku-4-5-20251001"
            
            custom_model = "claude-sonnet-3-5-20240620"
            options = create_nat_options("test_slug", "test_token", model=custom_model)
            
            # Check that ClaudeAgentOptions was called with custom model
            assert mock_options_class.call_args.kwargs["model"] == custom_model
        finally:
            if original_beta:
                os.environ["ANTHROPIC_BETA"] = original_beta
            else:
                os.environ.pop("ANTHROPIC_BETA", None)
