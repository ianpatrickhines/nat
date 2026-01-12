# Nat - The NationBuilder Assistant

An AI agent powered by Claude that provides natural language access to the NationBuilder V2 API.

## Features

- **60+ NationBuilder API tools** - Full coverage of the V2 API
- **Natural language interface** - Ask questions in plain English
- **Interactive mode** - Continuous conversation with context
- **Single query mode** - Perfect for scripts and automation

### Supported Operations

| Category | Operations |
|----------|------------|
| **People** | Search, create, update, delete signups; manage tags |
| **Contacts** | Log phone calls, emails, meetings, door knocks |
| **Donations** | Record, search, and manage donations |
| **Events** | Create events, manage RSVPs, track attendance |
| **Paths** | Assign people to paths, track journey progress |
| **Automations** | Enroll people, view enrollment status |
| **Lists** | View lists, add/remove members |
| **Surveys** | View surveys, record responses |
| **Petitions** | View petitions, add signatures |
| **Memberships** | Create and manage memberships |
| **Mailings** | View email blasts and broadcasters |

## Installation

```bash
# Clone or download the project
cd nat

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your credentials:
   ```
   ANTHROPIC_API_KEY=your_anthropic_api_key
   NATIONBUILDER_SLUG=your-nation-slug
   NATIONBUILDER_API_TOKEN=your_v2_api_token
   ```

### Getting Your API Keys

- **Anthropic API Key**: Get from [console.anthropic.com](https://console.anthropic.com/)
- **NationBuilder API Token**:
  1. Log into your nation's control panel
  2. Go to Settings → Developer → API Token
  3. Generate a V2 API token

## Usage

### Interactive Mode

```bash
python main.py
```

Start a conversation with Nat:

```
You: Find the person with email john@example.com
Nat: I found John Smith (ID: 12345) with email john@example.com...

You: Tag them as a volunteer
Nat: I've added the "volunteer" tag to John Smith.

You: exit
```

### Single Query Mode

```bash
python main.py --query "List all volunteers"
```

### Command Line Options

```
--query, -q    Single query mode
--slug         NationBuilder nation slug
--token        NationBuilder V2 API token
--model        Claude model (default: claude-sonnet-4-20250514)
```

## Example Queries

```
# People
"Find person by email john@example.com"
"Show me all volunteers"
"Create a new person named Jane Doe with email jane@example.com"
"Tag person 12345 as a donor"

# Donations
"List donations from last month"
"Record a $100 donation from person 12345"
"Show top donors"

# Events
"List upcoming events"
"RSVP person 12345 to event 67890"
"Show attendees for event 12345"

# Paths
"List available paths"
"Assign person 12345 to the volunteer onboarding path"
"Who is in step 2 of the donor cultivation path?"

# Lists
"Show all lists"
"Add person 12345 to the VIP list"
"Get members of the monthly donors list"
```

## Architecture

```
nat/
├── main.py              # Entry point
├── requirements.txt     # Dependencies
├── .env.example        # Environment template
└── src/nat/
    ├── __init__.py
    ├── agent.py        # Agent configuration and runners
    ├── client.py       # NationBuilder V2 API client
    └── tools.py        # 60+ tool definitions
```

## API Reference

The NationBuilder V2 API uses JSON:API format. Key concepts:

- **Resources**: signups, donations, events, paths, etc.
- **Filtering**: `filter[email]=test@example.com`
- **Pagination**: `page[size]=20&page[number]=1`
- **Sideloading**: `include=donations,signup_tags`
- **Sparse fields**: `fields[signups]=email,first_name`

## License

MIT
