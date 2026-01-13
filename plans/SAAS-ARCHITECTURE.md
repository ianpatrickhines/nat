# Nat SaaS Architecture Plan

> Transform Nat from a local CLI agent into a multi-tenant SaaS product that becomes the primary way NationBuilder customers interact with their nations.

## Vision

Nat is faster and more natural than the NationBuilder control panel. Non-technical users can accomplish in seconds what previously required navigating multiple screens and understanding NB's data model.

**Target market:** NationBuilder customers who aren't sophisticated enough to build this themselves. NB itself is unlikely to build something like this - it's not in their DNA.

## Business Model

### Pricing (Flat Rate MRR)

| Plan | Price | Target | Limits |
|------|-------|--------|--------|
| **Starter** | $49/mo | Small orgs, 1 user | 1 seat, 500 queries/mo soft cap |
| **Team** | $149/mo | Mid-size, campaigns | 5 seats, 2,000 queries/mo soft cap |
| **Organization** | $399/mo | Large orgs, parties | 15 seats, unlimited* |

*"Unlimited" = fair use policy, reach out if >10k queries/mo

### Unit Economics (at Haiku 4.5: $1/$5 per MTok)

| Metric | Starter | Team | Org |
|--------|---------|------|-----|
| MRR | $49 | $149 | $399 |
| Est. queries/mo | 200 | 800 | 3,000 |
| Claude cost (~$0.02/query) | ~$4 | ~$16 | ~$60 |
| **Gross margin** | **92%** | **89%** | **85%** |

Flat rate works because most users won't hit limits - they're paying for access, not consumption. Monitor heavy users and reach out personally.

### Risk Mitigation for Flat Rate

- Soft caps with friendly warnings, not hard cutoffs
- Fair use policy in ToS
- Per-minute rate limiting (prevent runaway loops)
- Weekly usage reports to identify outliers early
- Upgrade prompts when approaching limits

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLIENTS                                  │
├─────────────────────┬───────────────────┬───────────────────────┤
│   Chrome Extension  │    Slack Bot      │   Web App (future)    │
│   (NB CP overlay)   │   (team chat)     │   (standalone)        │
└─────────┬───────────┴─────────┬─────────┴───────────┬───────────┘
          │                     │                     │
          ▼                     ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                    API Gateway (REST/WebSocket)                  │
│                    api.nat.nationbuilder.tools                   │
└─────────────────────────────────────────────────────┬───────────┘
                                                      │
          ┌───────────────────────┬───────────────────┼───────────┐
          ▼                       ▼                   ▼           │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐ │
│   Auth Service  │    │   Nat Agent     │    │  Usage Tracker  │ │
│   (Cognito)     │    │   (ECS Fargate) │    │  (DynamoDB)     │ │
│                 │    │                 │    │                 │ │
│ - NB OAuth      │    │ - Claude SDK    │    │ - Query counts  │ │
│ - Session mgmt  │    │ - 66 tools      │    │ - Billing meter │ │
│ - Stripe link   │    │ - Per-tenant    │    │ - Rate limits   │ │
└─────────────────┘    └────────┬────────┘    └─────────────────┘ │
                                │                                  │
                    ┌───────────┴───────────┐                     │
                    ▼                       ▼                     │
          ┌─────────────────┐    ┌─────────────────┐              │
          │   Anthropic     │    │  NationBuilder  │              │
          │   Claude API    │    │   V2 API        │              │
          │   (Haiku 4.5)   │    │   (per tenant)  │              │
          └─────────────────┘    └─────────────────┘              │
                                                                   │
          ┌────────────────────────────────────────────────────────┘
          ▼
┌─────────────────┐
│  Stripe         │
│  - Subscriptions│
│  - Usage meters │
│  - Invoicing    │
└─────────────────┘
```

## AWS Stack

| Component | Service | Purpose |
|-----------|---------|---------|
| **Agent runtime** | ECS Fargate | Long-running WebSocket connections, streaming responses |
| **API** | API Gateway | REST + WebSocket support |
| **Auth** | Cognito | User pools, federated identity |
| **Storage** | DynamoDB | Sessions, usage tracking, tenant config |
| **Secrets** | Secrets Manager | NB tokens per tenant (encrypted) |
| **Queue** | SQS | Async task processing, scheduled jobs |
| **Scheduler** | EventBridge | Recurring automations (Phase 2) |
| **CDN** | CloudFront | Chrome extension assets, web app |
| **DNS** | Route 53 | api.nat.nationbuilder.tools |

### Cost Estimate (AWS)

| Component | Monthly Est. |
|-----------|--------------|
| ECS Fargate (2 tasks) | $30-50 |
| API Gateway | $10-20 |
| DynamoDB | $5-10 |
| Other (Cognito, Secrets, etc.) | $10-20 |
| **Total infrastructure** | **~$55-100/mo** |

Break-even: 2 Starter customers

## Client Applications

### Chrome Extension (Primary)

Floating chat panel that overlays on the NationBuilder control panel:

```
┌─────────────────────────────────────────────────────────┐
│ NationBuilder Control Panel                    [Nat 💬] │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  People > Ian Hines                                     │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Email: ian@hines.digital                        │   │
│  │ Tags: volunteer, donor                          │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 💬 Nat                                     ─ □ x │   │
│  │ ─────────────────────────────────────────────── │   │
│  │ You: Tag everyone who donated over $100 as      │   │
│  │      "major donor"                              │   │
│  │                                                 │   │
│  │ Nat: I found 23 people who donated over $100.   │   │
│  │      I'll add the "major donor" tag to each.    │   │
│  │      [Proceed] [Cancel]                         │   │
│  │                                                 │   │
│  │ [Type a message...]                      [Send] │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Features:**
- Floating, draggable chat panel
- Context-aware (knows current page/record in NB)
- Confirmation dialogs before bulk/destructive operations
- "Show me" links that navigate to relevant NB pages
- Keyboard shortcut to open (Cmd+K or similar)
- Streaming responses for real-time feedback

**Tech stack:**
- Manifest V3 (Chrome Extension)
- React or vanilla JS for UI
- WebSocket connection to API Gateway
- Chrome storage for session tokens

### Slack Bot (Secondary)

For teams that live in Slack:

```
#operations channel

@nat who donated this week?

Nat: 📊 This week's donations (Jan 6-12):
     • Sarah Chen - $250 (recurring)
     • Mike Johnson - $100
     • Anonymous - $50

     Total: $400 from 3 donors

     [View in NationBuilder →]
```

**Features:**
- Mention-based invocation (@nat)
- Thread replies for follow-ups
- Rich formatting (tables, links)
- Slash commands for common operations
- Multi-nation support (link Slack workspace to NB nation)

**Tech stack:**
- Slack Bolt SDK (Python)
- Lambda function for event handling
- Slack OAuth for workspace installation

## Multi-Tenancy Model

Each customer (NationBuilder nation) is a tenant:

```python
# Tenant record in DynamoDB
{
    "tenant_id": "uuid",                          # Primary key
    "stripe_customer_id": "cus_xxx",              # Stripe link
    "stripe_subscription_id": "sub_xxx",          # Active subscription
    "plan": "team",                               # starter|team|org

    # NationBuilder connection
    "nationbuilder_slug": "hddev3",
    "nationbuilder_token_arn": "arn:aws:secretsmanager:...",  # Encrypted

    # Limits
    "seats_limit": 5,
    "queries_soft_cap": 2000,

    # Usage (reset monthly)
    "queries_this_month": 847,
    "billing_cycle_start": "2025-01-01",

    # Users
    "users": [
        {"user_id": "uuid", "email": "ian@hines.digital", "role": "admin"},
        {"user_id": "uuid", "email": "staff@org.com", "role": "member"}
    ],

    # Metadata
    "created_at": "2025-01-12",
    "updated_at": "2025-01-12"
}
```

## Authentication Flow

### Initial Setup (Onboarding)

```
1. User signs up at nat.nationbuilder.tools
2. Stripe Checkout → creates subscription
3. Redirect to NationBuilder OAuth
4. User authorizes Nat to access their nation
5. We store encrypted NB token in Secrets Manager
6. User installs Chrome Extension
7. Extension authenticates via Cognito
8. Ready to use
```

### Per-Request Auth

```
1. Chrome Extension sends request with Cognito JWT
2. API Gateway validates JWT
3. Lambda/ECS looks up tenant by user_id
4. Retrieves NB token from Secrets Manager
5. Initializes Nat agent with tenant's credentials
6. Processes request, returns response
7. Increments usage counter in DynamoDB
```

## Phase 2: Scheduled Automations

Let Nat run recurring tasks:

```
You: Every Monday at 9am, send me a summary of new
     signups and donations from the past week.

Nat: I'll set that up. Every Monday at 9am I'll:
     1. Count new signups from the past 7 days
     2. Summarize donations (total, count, top donors)
     3. Send you a Slack message with the report

     [Enable weekly report]
```

### Implementation

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  EventBridge    │────▶│  Lambda         │────▶│  Nat Agent      │
│  (cron rule)    │     │  (trigger)      │     │  (execute task) │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
                                               ┌─────────────────┐
                                               │  Slack/Email    │
                                               │  (deliver)      │
                                               └─────────────────┘
```

### Scheduled Task Record

```python
{
    "task_id": "uuid",
    "tenant_id": "uuid",
    "name": "Weekly donation summary",
    "schedule": "cron(0 9 ? * MON *)",  # Every Monday 9am
    "prompt": "Summarize new signups and donations from the past 7 days",
    "delivery": {
        "type": "slack",
        "channel": "#operations"
    },
    "enabled": True,
    "last_run": "2025-01-06T09:00:00Z",
    "next_run": "2025-01-13T09:00:00Z"
}
```

## Roadmap

| Phase | Deliverable | Effort | Status |
|-------|-------------|--------|--------|
| **0** | Core agent (local CLI) | - | ✅ Done |
| **1** | Chrome Extension + Stripe + AWS | 2-3 weeks | Planning |
| **2** | Slack Bot | 1 week | - |
| **3** | Usage dashboard + admin | 1 week | - |
| **4** | Scheduled automations | 2 weeks | - |
| **5** | Web app (standalone) | 2 weeks | - |

## Open Questions

1. **Domain:** nat.nationbuilder.tools? natforbuilders.com? asknat.ai?
2. **NB Partnership:** Approach NB about official partnership/marketplace listing?
3. **SOC 2:** Required for enterprise customers? Timeline?
4. **Data residency:** Any customers need EU data residency?
5. **White-label:** Offer white-label version for agencies?

## Competitive Landscape

| Competitor | Threat Level | Notes |
|------------|--------------|-------|
| NationBuilder native AI | Medium | Not in their DNA, but possible |
| Generic AI assistants | Low | Can't easily integrate with NB API |
| Agencies building custom | Low | One-off, not productized |
| Zapier/Make.com | Low | Different use case (automation vs. interaction) |

## Success Metrics

| Metric | 3 months | 6 months | 12 months |
|--------|----------|----------|-----------|
| MRR | $1,000 | $5,000 | $20,000 |
| Customers | 20 | 75 | 250 |
| Queries/day | 500 | 2,000 | 10,000 |
| NPS | 40+ | 50+ | 60+ |

---

*Last updated: January 2025*
