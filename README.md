# Nat

**Stop clicking. Start asking.**

Nat is your AI-powered assistant for NationBuilder. Instead of navigating endless menus and filters, just tell Nat what you need in plain English.

## The Problem

NationBuilder is powerful, but let's be honest: the control panel is overwhelming. Finding a donor means clicking through People → Filters → Add condition → Amount → Greater than... You get the idea.

Your volunteers shouldn't need a training manual. Your staff shouldn't waste hours on data entry. You have doors to knock and calls to make.

## The Solution

Nat understands what you mean.

> **You:** "Who donated over $100 last month?"
>
> **Nat:** Found 23 people. Here they are...

> **You:** "Tag everyone who attended the rally as 'activist'"
>
> **Nat:** Done. Tagged 156 people.

> **You:** "Add a note that I called Sarah Chen about volunteering"
>
> **Nat:** Got it. Logged the contact.

No menus. No filters. No manual. Just results.

## What Nat Can Do

| Ask Nat to... | Instead of... |
|---------------|---------------|
| "Find John Smith" | People → Search → Type name → Click profile |
| "Show me this week's donations" | Finances → Donations → Filter by date → Apply |
| "Tag these people as volunteers" | Select all → Bulk actions → Add tag → Choose tag → Confirm |
| "Log a phone call with notes" | Click person → Contacts → New contact → Select type → Add notes → Save |
| "Who RSVPed to the fundraiser?" | Events → Find event → Click → RSVPs → Export |

Nat handles **60+ operations** across people, donations, events, tags, lists, paths, surveys, petitions, memberships, and more.

## Who It's For

- **Campaign staff** who need answers fast, not click-throughs
- **Nonprofit admins** juggling members, donors, and events
- **Volunteers** who want to help but find NationBuilder intimidating
- **Anyone** who'd rather talk than click

## See It In Action

```
You: Find everyone tagged "volunteer" in Austin

Nat: Found 47 volunteers in Austin:
     - Maria Garcia - Austin, TX
     - James Wilson - Austin, TX
     - Chen Wei - Austin, TX
     ... and 44 more

You: Add them all to the phone bank list

Nat: Added 47 people to "Phone Bank" list.

You: How many donations did we get this week?

Nat: This week: 12 donations totaling $2,340
     Top donor: Sarah Chen ($500)
     Average: $195
```

---

## Getting Started

### Requirements

- Python 3.10+
- A NationBuilder nation with API access
- An Anthropic API key ([get one here](https://console.anthropic.com/))

### Quick Setup

```bash
# Clone the repo
git clone https://github.com/ianpatrickhines/nat.git
cd nat

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure your keys
cp .env.example .env
# Edit .env with your credentials
```

### Configuration

Edit `.env` with:

```
ANTHROPIC_API_KEY=your_anthropic_api_key
NATIONBUILDER_SLUG=your-nation-slug
NATIONBUILDER_API_TOKEN=your_v2_api_token
```

**Getting your NationBuilder API token:**
1. Log into your nation's control panel
2. Go to Settings → Developer → API Token
3. Generate a V2 API token

### Run Nat

```bash
# Interactive conversation
python main.py

# Single question
python main.py --query "How many people are in my database?"
```

---

## Technical Details

<details>
<summary>For developers: Architecture and API reference</summary>

### Architecture

```
nat/
├── main.py              # Entry point
├── requirements.txt     # Dependencies
├── .env.example         # Environment template
└── src/nat/
    ├── agent.py         # Claude Agent SDK configuration
    ├── client.py        # NationBuilder V2 API client (JSON:API)
    └── tools.py         # 60+ tool definitions
```

### Powered By

- [Claude Agent SDK](https://docs.anthropic.com/en/docs/agents) - Anthropic's framework for building AI agents
- [NationBuilder V2 API](https://nationbuilder.com/api_documentation) - JSON:API format

### API Coverage

Full coverage of NationBuilder V2 API resources:
- Signups (people), Tags, Contacts
- Donations, Events, RSVPs
- Paths, Path Journeys, Automations
- Lists, Surveys, Petitions
- Memberships, Mailings, and more

### JSON:API Concepts

- **Filtering**: `filter[email]=test@example.com`
- **Pagination**: `page[size]=20&page[number]=1`
- **Sideloading**: `include=donations,signup_tags`
- **Sparse fields**: `fields[signups]=email,first_name`

</details>

---

## Coming Soon

Nat SaaS is in development — a hosted version with:
- **Chrome extension** that lives right inside your NationBuilder control panel
- **No setup required** — just install and connect
- **Team access** — multiple users per nation

Interested? [Get notified when we launch](mailto:ian@hines.digital?subject=Nat%20SaaS%20Interest).

---

## License

[O'Sassy License](LICENSE.md) — Open source with SaaS rights reserved.

You're free to use, modify, and self-host Nat. You cannot offer it as a competing hosted service.

---

Built with care by [Hines Digital](https://hines.digital)
