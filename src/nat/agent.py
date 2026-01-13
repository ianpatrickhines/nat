"""
Nat - The NationBuilder Assistant Agent

Main agent implementation using the Claude Agent SDK.
Provides natural language access to the NationBuilder V2 API.
"""

import os
import logging
from typing import Any

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    create_sdk_mcp_server,
    AssistantMessage,
    TextBlock,
    ResultMessage,
)

from .client import init_client
from .tools import ALL_TOOLS

logger = logging.getLogger(__name__)


# System prompt for Nat
SYSTEM_PROMPT = """You are Nat, an expert NationBuilder assistant. You help users manage their nation's database of people, donations, events, paths, and more through natural language.

## Your Capabilities

You have access to 60+ tools for interacting with the NationBuilder V2 API:

### People Management (Signups)
- Search and list people by email, name, phone, volunteer status, donor status
- Create, update, and delete person records
- Manage tags on people
- View and log contact history (phone calls, emails, meetings, etc.)

### Fundraising
- List and search donations
- Record new donations
- Manage pledges
- View donation tracking codes for campaign attribution

### Events
- List and search events
- Create and manage events
- RSVP people to events
- Track attendance

### Paths & Workflows
- View available paths (workflows)
- Assign people to paths
- Update path journey progress
- Track who is at which step

### Automations
- List automations
- Enroll people in automations
- View enrollment status

### Lists & Segments
- View saved lists
- Get list members
- Add/remove people from lists

### Surveys & Petitions
- View surveys and questions
- Record survey responses
- View petitions
- Add petition signatures

### Memberships
- View membership types
- Create memberships for people
- Track membership status

### Communications
- View mailings/email blasts
- View broadcasters

## Guidelines

1. **Always confirm before destructive operations** - Ask before deleting records
2. **Start searches with filters** - Use email or name filters when searching for people
3. **Use sideloading** - Include related data to reduce API calls (e.g., include donations when getting a person)
4. **Page through results** - For large datasets, use pagination
5. **Respect privacy preferences** - Note do_not_contact and do_not_call flags
6. **Format responses clearly** - Present data in a readable format

## JSON:API Format

NationBuilder uses JSON:API. Responses have this structure:
- `data`: The resource(s) - contains `id`, `type`, and `attributes`
- `included`: Sideloaded related resources
- `links`: Pagination links (self, prev, next)

## Examples

**Finding a person by email:**
"Find the person with email john@example.com"
→ Use list_signups with filter: {"email": "john@example.com"}

**Adding a tag:**
"Tag John Smith as a volunteer"
→ First find John, then use tag_signup with their ID

**Recording a donation:**
"Record a $100 donation from signup 12345"
→ Use create_donation with amount_in_cents: 10000

**RSVP to event:**
"RSVP person 12345 to event 67890"
→ Use create_event_rsvp with event_id and signup_id
"""


def get_tool_names() -> list[str]:
    """Get the list of allowed tool names for the MCP server."""
    return [f"mcp__nationbuilder__{tool.name}" for tool in ALL_TOOLS]


def _setup_prompt_caching() -> None:
    """
    Configure environment for Claude API prompt caching.
    
    Prompt caching can reduce costs by up to 90% for cached content.
    This function sets up the necessary environment variables to enable
    prompt caching when supported by the Claude Agent SDK.
    
    See: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
    """
    # Check if caching is explicitly disabled
    if os.environ.get("NAT_DISABLE_PROMPT_CACHING", "").lower() == "true":
        logger.info("Prompt caching disabled via NAT_DISABLE_PROMPT_CACHING")
        return
    
    # Enable prompt caching beta feature
    # This sets the anthropic-beta header to "prompt-caching-2024-07-31"
    existing_beta = os.environ.get("ANTHROPIC_BETA", "")
    if "prompt-caching" not in existing_beta:
        new_beta = "prompt-caching-2024-07-31"
        if existing_beta:
            new_beta = f"{existing_beta},prompt-caching-2024-07-31"
        os.environ["ANTHROPIC_BETA"] = new_beta
        logger.info(f"Enabled prompt caching: ANTHROPIC_BETA={new_beta}")
    else:
        logger.info("Prompt caching already enabled")


def create_nat_options(
    slug: str,
    token: str,
    model: str = "claude-haiku-4-5-20251001",
    enable_caching: bool = True
) -> ClaudeAgentOptions:
    """
    Create ClaudeAgentOptions configured for Nat.

    Args:
        slug: NationBuilder nation slug
        token: NationBuilder V2 API token
        model: Claude model to use
        enable_caching: Whether to enable prompt caching (default: True)

    Returns:
        Configured ClaudeAgentOptions
    """
    # Enable prompt caching if requested
    if enable_caching:
        _setup_prompt_caching()
    
    # Initialize the NationBuilder client
    init_client(slug, token)

    # Create the MCP server with all tools
    nationbuilder_server = create_sdk_mcp_server(
        name="nationbuilder",
        version="1.0.0",
        tools=ALL_TOOLS
    )

    return ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={"nationbuilder": nationbuilder_server},
        allowed_tools=get_tool_names(),
        model=model
    )


async def run_nat_interactive(
    slug: str,
    token: str,
    model: str = "claude-haiku-4-5-20251001"
) -> None:
    """
    Run Nat in interactive mode with continuous conversation.

    Args:
        slug: NationBuilder nation slug
        token: NationBuilder V2 API token
        model: Claude model to use
    """
    options = create_nat_options(slug, token, model)

    print("=" * 60)
    print("  Nat - The NationBuilder Assistant")
    print("=" * 60)
    print("\nI can help you manage your NationBuilder nation.")
    print("Type 'exit' or 'quit' to end the session.")
    print("Type 'help' for a list of capabilities.\n")

    async with ClaudeSDKClient(options=options) as client:
        while True:
            try:
                user_input = input("\nYou: ").strip()

                if not user_input:
                    continue

                if user_input.lower() in ("exit", "quit"):
                    print("\nGoodbye!")
                    break

                if user_input.lower() == "help":
                    print(_get_help_text())
                    continue

                # Send query to Nat
                await client.query(user_input)

                # Process and display response
                print("\nNat: ", end="", flush=True)
                async for message in client.receive_response():
                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                print(block.text, end="", flush=True)
                    elif isinstance(message, ResultMessage):
                        if message.is_error:
                            print(f"\n[Error: {message.result}]")
                print()  # Newline after response

            except KeyboardInterrupt:
                print("\n\nSession interrupted. Goodbye!")
                break
            except Exception as e:
                print(f"\n[Error: {e}]")


async def query_nat(
    prompt: str,
    slug: str,
    token: str,
    model: str = "claude-haiku-4-5-20251001"
) -> str:
    """
    Send a single query to Nat and return the response.

    Args:
        prompt: The user's question or command
        slug: NationBuilder nation slug
        token: NationBuilder V2 API token
        model: Claude model to use

    Returns:
        Nat's response as a string
    """
    options = create_nat_options(slug, token, model)

    response_parts: list[str] = []

    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)

        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        response_parts.append(block.text)

    return "".join(response_parts)


def _get_help_text() -> str:
    """Return help text for interactive mode."""
    return """
Nat can help you with:

PEOPLE
  "Find person by email john@example.com"
  "Show me all volunteers"
  "Create a new person named Jane Doe"
  "Tag person 12345 as a donor"

DONATIONS
  "List donations from last month"
  "Record a $100 donation from person 12345"
  "Show donation totals"

EVENTS
  "List upcoming events"
  "RSVP person 12345 to event 67890"
  "Show attendees for event 12345"

PATHS
  "List available paths"
  "Assign person 12345 to the volunteer onboarding path"
  "Who is in the donor cultivation path?"

LISTS
  "Show all lists"
  "Add person 12345 to the VIP list"
  "Get members of the monthly donors list"

SURVEYS
  "Show survey 12345 with questions"
  "Record survey response for person 12345"

Type your question in natural language and I'll help!
"""
