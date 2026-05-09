# Nat - NationBuilder Assistant

## Overview

Nat is a conversational AI assistant that provides natural language access to NationBuilder's V2 API. It lives as a Chrome extension sidebar that overlays on the NationBuilder control panel, transforming how non-technical users interact with their nations.

**Target user:** Political volunteers and nonprofit admins who find NationBuilder's control panel overwhelming - too many buttons, too many filters, too many layers deep to accomplish tasks.

**Value proposition:** Tasks that previously required navigating multiple screens and understanding NB's data model can be accomplished in seconds through conversation.

**Business model:** Flat-rate MRR subscription ($49/$149/$399 tiers) with query-based soft caps.

**Success criteria:** 10 paying customers with low churn (retention > 30 days).

---

## Product Requirements

### MVP Scope

**In scope (MVP):**
- Chrome extension with fixed sidebar (350px)
- Tutorial walkthrough for first-time users
- All 66 NationBuilder V2 API tools
- Per-user NB OAuth authentication
- Stripe subscription billing
- Query-based usage caps (hard limits)
- Context-aware page detection (all major NB page types)
- Confirmation dialogs for destructive/bulk operations
- Session undo for recent actions
- Background job execution (jobs continue even if tab closes)

**Out of scope (Phase 2+):**
- Slack bot integration
- Scheduled automations
- Firefox/Safari/Edge support
- Mobile support
- Data export functionality
- Multi-user team features (beyond basic seat management)
- Advanced analytics dashboard

### Chrome Extension

#### Appearance
- **Position:** Fixed sidebar, docked to right edge of browser
- **Width:** 350px (balanced between usability and NB space)
- **Default state:** Open with chat visible
- **Collapsible:** Toggle to thin strip (icon + status indicator)
- **Keyboard shortcut:** Cmd+K / Ctrl+K to toggle (overrides NB if conflict)

#### Tutorial Flow
First-time users see a guided walkthrough:
1. Welcome + what Nat can do
2. Example queries with real results from their nation
3. How to ask for help
4. How confirmations work for dangerous operations

After tutorial: Nat sidebar remains open, ready for queries.

#### Context Awareness
- Detect current NB page type (person profile, list, event, donation, path, etc.)
- Auto-scope queries to current context ("tag this person" knows who you're viewing)
- Show context hint at top of sidebar ("Viewing: Ian Hines")
- Suggest relevant actions based on current page

#### Domains
- Runs only on `*.nationbuilder.com`
- Does not support custom domains at MVP

### Conversation UX

#### Input/Output
- Single text input field
- Streaming responses (SSE) - shows Nat "typing"
- Results display: name, city/state, summary stat, link to NB profile
- **No PII in chat:** No email, phone, or full address displayed
- No file exports - redirect users to NB's export features

#### Confirmations
Before executing destructive or bulk operations:
- Show summary of what will happen
- Present options: [Proceed] [Cancel]
- Similar UX to Claude Code's AskUserQuestion tool

#### Session Undo
- Nat remembers actions taken in current session
- User can say "undo that" to reverse recent actions
- Session memory clears when tab closes
- Undo only works for actions Nat took (not manual NB actions)

#### Error Handling
- Natural language error messages
- No technical details unless specifically asked
- Capability gaps: suggest alternatives ("I can't send email, but I can add them to a list")
- Permission denied: explain limitation ("Your NB account doesn't have permission to delete donations")

#### Name Search and Ambiguity
- Full name search supported (name, email, phone - whatever NB supports)
- Multiple matches: "I found 3 John Smiths. Which one?" with list
- Context-first when ambiguous: if user recently viewed a John Smith in NB, suggest that one

#### Long-Running Operations
- Run in background (Lambda continues regardless of tab state)
- Toast notification when complete
- On tab reopen: show pending/completed background job results, then fresh start

#### Multi-Tab Behavior
- Unified session across tabs
- Page context syncs to whichever tab is active
- Same conversation regardless of which tab is focused

### Rate Limiting and Abuse

- **Cooldown:** If user sends messages too quickly, enforce 5-second wait between messages
- **Query = user message:** Each message sent counts as one query (multi-turn tool use in response = 1 query)
- **Monthly caps:** Hard stop at cap, must upgrade to continue
- **Anomaly detection:** Flag unusual patterns (rapid queries, bulk lookups) for manual review
- NB permissions already limit what data can be accessed

### Personality and Tone

- **Name:** Nat (short for NATionBuilder)
- **Tone:** Professional helper - polite, efficient, no personality flourishes
- **Uncertainty:** Admit limits - "I'm not sure how to do that. Try [suggestion] or contact NB support."
- No emojis unless user requests them

---

## Business Requirements

### Pricing Tiers

| Plan | Price | Seats | Queries/mo | Target |
|------|-------|-------|------------|--------|
| **Starter** | $49/mo | 1 | 500 | Small orgs, individual users |
| **Team** | $149/mo | 5 | 2,000 | Mid-size campaigns |
| **Organization** | $399/mo | 15 | 5,000 | Large orgs, parties |

### Billing Model

- **No free trial:** Users pay immediately (MRR priority, API costs)
- **Refunds:** Manual review, case-by-case
- **Query caps:** Hard limits - user must upgrade to continue
- **Plan selection:** Pricing page comparison, then direct link to selected plan's Stripe Checkout

### Subscription Management

- **Plan changes:** Stripe Customer Portal handles upgrades/downgrades
- **Payment failures:** Immediate lockout
- **Lockout UX:** Reason + fix action ("Payment failed. [Update card]")
- **Churn:** No grace period - access ends when subscription ends

### Team Management (Team/Org plans)

- **User auth:** Per-user NationBuilder OAuth (actions attributed to individual)
- **Invites:** Email invite flow - admin invites, recipient clicks, authenticates with own NB account
- **Conversation privacy:** Private per-user - each user sees only their own history
- **Action attribution:** Actions recorded via API as if the authenticated user did them (not "Nat did it")

### Entity and Operations

- **Operating entity:** Hines Digital (for now; new LLC if revenue supports it later)
- **Support:** Email only (support@[domain])
- **Legal:** AI-generated Terms of Service and Privacy Policy (reviewed before launch)

### Distribution

- **Primary:** NationBuilder community (forums, Facebook groups)
- **Secondary:** NationBuilder partnership/marketplace listing
- Chrome Web Store listing

---

## Technical Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Chrome Extension (Preact)                     │
│                    - Fixed 350px sidebar                         │
│                    - Manifest V3                                 │
│                    - SSE for streaming                           │
└─────────────────────────────────────────────────────────────────┘
                                │
                                │ HTTPS + SSE
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    API Gateway (REST + SSE)                      │
│                    api.[domain]                                  │
└─────────────────────────────────────────────────────────────────┘
                                │
          ┌─────────────────────┼─────────────────────┐
          ▼                     ▼                     ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│  Auth Lambda    │   │   Nat Lambda    │   │ Webhook Lambda  │
│  (NB OAuth)     │   │   (Agent)       │   │ (Stripe)        │
│                 │   │                 │   │                 │
│ - Token exchange│   │ - Claude SDK    │   │ - Sub events    │
│ - Refresh       │   │ - 66 tools      │   │ - Usage updates │
└─────────────────┘   └────────┬────────┘   └─────────────────┘
                               │
                    ┌──────────┴──────────┐
                    ▼                     ▼
          ┌─────────────────┐   ┌─────────────────┐
          │   Anthropic     │   │  NationBuilder  │
          │   Claude API    │   │   V2 API        │
          │   (Haiku 4.5)   │   │   (per user)    │
          └─────────────────┘   └─────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                         AWS Services                             │
├─────────────────┬─────────────────┬─────────────────────────────┤
│   DynamoDB      │ Secrets Manager │   EventBridge               │
│   - Tenants     │ - NB tokens     │   - Token refresh (12h)     │
│   - Usage       │ - Stripe keys   │                             │
│   - Users       │ - NB client     │                             │
└─────────────────┴─────────────────┴─────────────────────────────┘
```

### AWS Services

| Component | Service | Purpose |
|-----------|---------|---------|
| **Agent runtime** | Lambda | Query processing, Claude SDK |
| **API** | API Gateway | REST endpoints, SSE streaming |
| **Auth callback** | Lambda | NB OAuth token exchange |
| **Token refresh** | Lambda + EventBridge | Proactive 12h refresh |
| **Webhook handler** | Lambda | Stripe subscription events |
| **Data storage** | DynamoDB | Tenants, users, usage |
| **Secrets** | Secrets Manager | NB tokens, Stripe keys, NB client credentials |
| **IaC** | CloudFormation | All infrastructure |

### Environments

- **dev:** Development and testing
- **staging:** Pre-production validation
- **prod:** Production

### CI/CD

- **Platform:** GitHub Actions
- **Pipeline:** Push to main → test → deploy to staging → manual approval → deploy to prod

### Authentication Flow

#### User Identity
- Stripe customer = user identity at MVP
- Email from Stripe checkout used for authentication
- Extension authenticates via magic link or Stripe session token
- No separate user database for MVP

#### NationBuilder OAuth
Per-user OAuth (not per-org):
1. User installs extension → extension detects no NB connection
2. Extension shows "Connect NationBuilder" → redirect to NB OAuth
3. NB OAuth → callback Lambda → token exchange
4. Tokens stored in Secrets Manager
5. DynamoDB updated with connection status

#### Token Management
- V2 tokens expire in 24 hours
- EventBridge triggers refresh Lambda every 12 hours
- Refresh tokens are single-use (store new refresh token after each refresh)
- Failed refresh → mark `nb_needs_reauth` → extension shows reconnect banner

### Data Model

#### Tenants Table (DynamoDB)
```python
{
    "tenant_id": "uuid",                       # PK
    "stripe_customer_id": "cus_xxx",
    "stripe_subscription_id": "sub_xxx",
    "stripe_subscription_status": "active",
    "plan": "starter",                         # starter|team|org
    "email": "user@example.com",

    # Usage (per billing cycle)
    "queries_this_month": 127,
    "queries_limit": 500,
    "billing_cycle_start": "2025-01-01",

    # Metadata
    "created_at": "2025-01-12T...",
    "updated_at": "2025-01-12T..."
}
```

#### Users Table (DynamoDB)
```python
{
    "user_id": "uuid",                         # PK
    "tenant_id": "uuid",                       # GSI
    "email": "user@example.com",
    "role": "admin",                           # admin|member

    # NationBuilder OAuth
    "nationbuilder_slug": "myorg",
    "nb_connected": True,
    "nb_connected_at": "2025-01-12T...",
    "nb_token_expires_at": 1736786400,
    "nb_needs_reauth": False,
    # Actual tokens in Secrets Manager: nat/user/{user_id}/nb-tokens

    # Metadata
    "created_at": "2025-01-12T...",
    "last_active_at": "2025-01-12T..."
}
```

### Chrome Extension Architecture

#### Technology
- **Framework:** Preact (3KB, React-compatible)
- **Manifest:** V3 (required for new extensions)
- **Build:** Vite or similar bundler
- **State:** Local component state (no Redux needed)

#### Content Script
- Injects sidebar into NB pages
- Detects current page context (URL patterns, DOM scraping)
- Communicates with background service worker

#### Background Service Worker
- Manages authentication state
- Handles SSE connection to API
- Broadcasts messages to content scripts

#### Storage
- Chrome storage API for session token
- No conversation history persisted (fully ephemeral)

### Security

- **Transport:** HTTPS only
- **Tokens:** Stored in AWS Secrets Manager, not DynamoDB
- **PII:** Not logged, not displayed in full (name + city/state only)
- **Audit:** Actions recorded via NB API as authenticated user
- **GDPR:** Data processor only - no data retention beyond session

---

## Onboarding Flow

```
1. User discovers Nat (NB community, partnership)
           │
           ▼
2. Pricing page → select plan → "Subscribe" button
           │
           ▼
3. Stripe Checkout → payment
           │
           ▼
4. Success page: "Install Chrome Extension" + link
           │
           ▼
5. Chrome Web Store → install extension
           │
           ▼
6. Extension detects no NB connection → "Connect NationBuilder"
           │
           ▼
7. NB OAuth flow → authorize Nat
           │
           ▼
8. OAuth callback → tokens stored → redirect back to NB
           │
           ▼
9. Extension shows tutorial walkthrough
           │
           ▼
10. Tutorial complete → Nat ready to use
```

---

## Edge Cases

### Extension Without Payment
- User installs extension but hasn't paid
- Extension shows: "Please subscribe first" + link to Stripe
- Completely blocked - no demo mode

### Subscription Lapsed
- Payment fails or user cancels
- Immediate lockout
- Extension shows: "Payment failed. [Update card]" or "Subscription cancelled. [Reactivate]"

### NB Token Expired
- Background refresh should prevent this
- If refresh fails: `nb_needs_reauth = true`
- Extension shows: "Nat lost access to your NationBuilder. [Reconnect]"
- Clicking reconnect triggers full OAuth flow again

### NB API Down
- Clear error: "NationBuilder isn't responding right now. Try again in a few minutes."
- No automatic retry

### Claude API Down
- Clear error: "Nat is temporarily unavailable. Please try again shortly."
- No fallback model

### Multiple John Smiths
- Show all matches with disambiguating info
- Let user select the correct one
- Don't guess or auto-select

### Bulk Operation Failure
- If partial failure during bulk operation
- Report what succeeded vs. failed
- Provide clear accounting ("Tagged 47/50 people. 3 failed: [list reasons]")

### User Asks for Unsupported Action
- "I can't do that, but I can [alternative]"
- Or: "That's outside what I can help with. Try [NB feature/support]"

---

## Testing Strategy

### Unit Tests
- All 66 NB API tool wrappers
- Token refresh logic
- Usage tracking/billing logic
- Query counting

### Integration Tests
- OAuth flow (mock NB)
- Stripe webhook handling
- End-to-end query flow (mock Claude + NB)

### E2E Tests
- Full onboarding flow (Playwright)
- Extension sidebar rendering
- Context detection on NB pages
- Conversation round-trip

### Test Environments
- Use separate NB test nation for staging
- Stripe test mode for payment testing
- Mock/sandbox Anthropic API for load testing

---

## Open Questions

1. **Domain name:** Need to secure domain (nat.example.com, asknat.ai, etc.)
2. **NB App Registration:** Need to register OAuth app in NationBuilder for each environment
3. **Stripe Account:** Need to create Stripe account and products
4. **Extension Review:** Chrome Web Store review timeline (can take days)
5. **NB Partnership:** When/how to approach NB about official partnership

---

## Decision Log

| Decision | Rationale | Alternatives Considered |
|----------|-----------|------------------------|
| Lambda over ECS | Simpler for MVP, pay-per-use aligns with business model, queries complete in seconds | ECS Fargate (better for WebSocket), EC2 (more control) |
| Preact over React | 3KB vs 45KB bundle, React-compatible API | React (larger), Vanilla JS (no tooling), Svelte (build complexity) |
| Stripe-linked auth | Avoid separate user database at MVP, simplest path | Cognito (complex), Auth0/Clerk (cost), custom JWT (maintenance) |
| REST + SSE over WebSocket | Simpler, works with Lambda, no connection management | WebSocket (realtime but complex), REST + polling (no streaming) |
| Hard query caps | Predictable costs, simple to implement, upgrade incentive | Soft caps (abuse risk), overage billing (complex) |
| No free trial | MRR priority, API costs, low price reduces risk | 7-day trial (costs), freemium (abuse) |
| Per-user NB OAuth | Action attribution, multi-user audit trail | Org-level OAuth (simpler but no attribution) |
| Session undo only | Achievable at MVP, covers "oops" moments | Full undo stack (complex), no undo (poor UX) |
| Python backend | Matches existing Nat code, Claude SDK works well | TypeScript (type safety), both (complexity) |

---

*Last updated: January 2025*
