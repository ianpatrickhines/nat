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

### Overview

Nat requires two layers of authentication:
1. **User auth** - Cognito JWT for API access (who is making the request)
2. **NationBuilder auth** - OAuth2 tokens for NB API access (what nation to access)

### Initial Setup (Onboarding)

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│  User   │     │   Nat   │     │ Stripe  │     │   NB    │     │   Nat   │
│         │     │  Site   │     │Checkout │     │  OAuth  │     │ Backend │
└────┬────┘     └────┬────┘     └────┬────┘     └────┬────┘     └────┬────┘
     │               │               │               │               │
     │  1. Sign up   │               │               │               │
     │──────────────>│               │               │               │
     │               │               │               │               │
     │  2. Redirect  │               │               │               │
     │<──────────────│               │               │               │
     │               │               │               │               │
     │  3. Pay       │               │               │               │
     │──────────────────────────────>│               │               │
     │               │               │               │               │
     │  4. Success + redirect        │               │               │
     │<──────────────────────────────│               │               │
     │               │               │               │               │
     │  5. Redirect to NB OAuth      │               │               │
     │───────────────────────────────────────────────>│               │
     │               │               │               │               │
     │  6. Authorize Nat             │               │               │
     │<──────────────────────────────────────────────│               │
     │               │               │               │               │
     │  7. Callback with code        │               │               │
     │──────────────────────────────────────────────────────────────>│
     │               │               │               │               │
     │               │               │  8. Exchange code for tokens  │
     │               │               │               │<──────────────│
     │               │               │               │               │
     │               │               │  9. Return tokens             │
     │               │               │               │──────────────>│
     │               │               │               │               │
     │  10. Success! Install extension               │               │
     │<──────────────────────────────────────────────────────────────│
     │               │               │               │               │
```

### NationBuilder OAuth2 Flow (V2 API)

NationBuilder uses standard OAuth2 authorization code flow with refresh tokens.

#### Step 1: Authorization Request

Redirect user to NationBuilder authorization page:

```
GET https://{slug}.nationbuilder.com/oauth/authorize
    ?response_type=code
    &client_id={client_id}
    &redirect_uri={callback_url}
    &state={tenant_id}
```

| Parameter | Value | Notes |
|-----------|-------|-------|
| `response_type` | `code` | Always "code" for auth code flow |
| `client_id` | From NB app registration | Register at Settings > Developer > Apps |
| `redirect_uri` | `https://api.nat.../oauth/callback` | Must be pre-registered in NB |
| `state` | `{tenant_id}` | Pass tenant ID through OAuth flow |

#### Step 2: User Authorization

User sees NationBuilder consent screen:
- "Nat wants to access your nation"
- User must be admin to authorize
- On approval, NB redirects to callback with auth code

#### Step 3: Token Exchange

```
POST https://{slug}.nationbuilder.com/oauth/token
Content-Type: application/json

{
    "grant_type": "authorization_code",
    "code": "{auth_code}",
    "client_id": "{client_id}",
    "client_secret": "{client_secret}",
    "redirect_uri": "{callback_url}"
}
```

#### Step 4: Token Response

```json
{
    "access_token": "abc123...",
    "refresh_token": "def456...",
    "token_type": "bearer",
    "expires_in": 86400,
    "created_at": 1736700000,
    "scope": "default"
}
```

**Important:** V2 API tokens expire in **24 hours** (86400 seconds).

#### Step 5: Token Refresh

V2 tokens must be refreshed before expiration. Refresh tokens are **single-use** (revoked after use).

```
POST https://{slug}.nationbuilder.com/oauth/token
Content-Type: application/json

{
    "grant_type": "refresh_token",
    "refresh_token": "{refresh_token}",
    "client_id": "{client_id}",
    "client_secret": "{client_secret}"
}
```

Response includes new `access_token` and `refresh_token`.

### OAuth Callback Handler (Lambda)

Based on existing pattern from `conduitstreetservices/shared/auth/nationbuilder-oauth-callback/`:

```python
# /oauth/callback Lambda handler
def lambda_handler(event, context):
    # 1. Extract code and tenant_id from callback
    code = event['queryStringParameters']['code']
    tenant_id = event['queryStringParameters']['state']

    # 2. Look up tenant to get nation slug
    tenant = dynamodb.get_item(Key={'tenant_id': tenant_id})
    nation_slug = tenant['nationbuilder_slug']

    # 3. Exchange code for tokens
    tokens = exchange_code_for_tokens(
        slug=nation_slug,
        code=code,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=CALLBACK_URL
    )

    # 4. Store tokens in Secrets Manager
    secrets_manager.put_secret_value(
        SecretId=f"nat/tenant/{tenant_id}/nb-tokens",
        SecretString=json.dumps({
            'access_token': tokens['access_token'],
            'refresh_token': tokens['refresh_token'],
            'expires_at': tokens['created_at'] + tokens['expires_in']
        })
    )

    # 5. Update tenant record
    dynamodb.update_item(
        Key={'tenant_id': tenant_id},
        UpdateExpression='SET nb_connected = :true, nb_connected_at = :now',
        ExpressionAttributeValues={':true': True, ':now': now()}
    )

    # 6. Redirect to success page
    return redirect('https://nat.../setup/success')
```

### Token Refresh Service

Background Lambda runs every 12 hours to proactively refresh expiring tokens:

```python
# EventBridge: rate(12 hours) → Lambda
def refresh_expiring_tokens(event, context):
    # Find tokens expiring in next 12 hours
    expiring_soon = now() + timedelta(hours=12)

    tenants = dynamodb.scan(
        FilterExpression='nb_token_expires_at < :soon',
        ExpressionAttributeValues={':soon': expiring_soon.timestamp()}
    )

    for tenant in tenants['Items']:
        try:
            # Get current tokens from Secrets Manager
            secret = secrets_manager.get_secret_value(
                SecretId=f"nat/tenant/{tenant['tenant_id']}/nb-tokens"
            )
            tokens = json.loads(secret['SecretString'])

            # Refresh the token
            new_tokens = refresh_nb_token(
                slug=tenant['nationbuilder_slug'],
                refresh_token=tokens['refresh_token']
            )

            # Store new tokens
            secrets_manager.put_secret_value(
                SecretId=f"nat/tenant/{tenant['tenant_id']}/nb-tokens",
                SecretString=json.dumps(new_tokens)
            )

            # Update expiry in DynamoDB for querying
            dynamodb.update_item(
                Key={'tenant_id': tenant['tenant_id']},
                UpdateExpression='SET nb_token_expires_at = :exp',
                ExpressionAttributeValues={':exp': new_tokens['expires_at']}
            )

        except Exception as e:
            # Token refresh failed - mark tenant for re-auth
            dynamodb.update_item(
                Key={'tenant_id': tenant['tenant_id']},
                UpdateExpression='SET nb_needs_reauth = :true',
                ExpressionAttributeValues={':true': True}
            )
            # Notify user via email/Slack
            notify_reauth_required(tenant)
```

### Re-Authorization Flow

When token refresh fails (user revoked access, etc.):

1. Set `nb_needs_reauth = true` in tenant record
2. Chrome Extension checks this flag on each request
3. Show banner: "Nat lost access to your NationBuilder. [Reconnect]"
4. User clicks → redirect to NB OAuth flow again
5. On success, clear `nb_needs_reauth` flag

### Per-Request Auth

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  Chrome  │     │   API    │     │  Lambda  │     │ Secrets  │     │    NB    │
│Extension │     │ Gateway  │     │  / ECS   │     │ Manager  │     │   API    │
└────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘
     │                │                │                │                │
     │ 1. Request +   │                │                │                │
     │    Cognito JWT │                │                │                │
     │───────────────>│                │                │                │
     │                │                │                │                │
     │                │ 2. Validate JWT│                │                │
     │                │   (Authorizer) │                │                │
     │                │───────────────>│                │                │
     │                │                │                │                │
     │                │                │ 3. Lookup      │                │
     │                │                │    tenant      │                │
     │                │                │────────────────│                │
     │                │                │                │                │
     │                │                │ 4. Get NB      │                │
     │                │                │    tokens      │                │
     │                │                │───────────────>│                │
     │                │                │                │                │
     │                │                │ 5. Init Nat    │                │
     │                │                │    agent       │                │
     │                │                │────────────────│                │
     │                │                │                │                │
     │                │                │ 6. Call NB API │                │
     │                │                │───────────────────────────────>│
     │                │                │                │                │
     │                │                │ 7. Response    │                │
     │                │                │<───────────────────────────────│
     │                │                │                │                │
     │ 8. Stream      │                │                │                │
     │    response    │                │                │                │
     │<───────────────│<───────────────│                │                │
     │                │                │                │                │
```

### DynamoDB Schema (Updated)

```python
# Tenants table
{
    "tenant_id": "uuid",                      # PK
    "stripe_customer_id": "cus_xxx",
    "stripe_subscription_id": "sub_xxx",
    "plan": "team",

    # NationBuilder OAuth
    "nationbuilder_slug": "hddev3",
    "nationbuilder_client_id": "xxx",         # App credentials (shared or per-tenant)
    "nb_connected": True,
    "nb_connected_at": "2025-01-12T...",
    "nb_token_expires_at": 1736786400,        # For refresh job queries
    "nb_needs_reauth": False,                 # True if refresh failed

    # Tokens stored in Secrets Manager, not DynamoDB
    # Secret: nat/tenant/{tenant_id}/nb-tokens

    # Limits & Usage
    "seats_limit": 5,
    "queries_soft_cap": 2000,
    "queries_this_month": 847,
    "billing_cycle_start": "2025-01-01",

    # Users
    "users": [...],

    # Metadata
    "created_at": "2025-01-12",
    "updated_at": "2025-01-12"
}
```

### Security Considerations

1. **Token storage** - NB tokens in Secrets Manager, not DynamoDB
2. **Client secret** - Stored in Secrets Manager, never in code
3. **PKCE** - Consider implementing for additional OAuth security
4. **Scope** - Request minimal scope ("default" is fine for V2)
5. **Token rotation** - Refresh tokens are single-use, always store new one
6. **Audit log** - Log all OAuth events (connect, refresh, revoke)

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
