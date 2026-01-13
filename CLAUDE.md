# Nat Architecture Documentation

## Overview

Nat is an AI-powered assistant for NationBuilder that helps users manage their nation data through natural language queries. The system uses a **nation-based billing model** where subscriptions are tied to NationBuilder organizations (nations) rather than individual users.

## Architecture Model: Per-Nation Billing

### Core Principle

**Any user authenticated to a NationBuilder nation can use Nat if that nation has an active subscription.**

This aligns with how NationBuilder itself operates - access is based on organization membership, not individual subscriptions.

### Pricing

| Plan | Price | Queries | Access |
|------|-------|---------|--------|
| Nat | $29/mo | 500/mo | Everyone on the nation |
| Nat Pro | $79/mo | Unlimited | Everyone on the nation |

### Key Components

## 1. Data Model

### NationsTable (DynamoDB)
Primary table for nation-level subscription and usage data.

```yaml
PK: nation_slug (e.g., "yournation")
Attributes:
  - nation_slug: string (PK)
  - stripe_customer_id: string (GSI)
  - stripe_subscription_id: string
  - subscription_status: "active" | "trialing" | "cancelled" | "none"
  - subscription_plan: "nat" | "nat_pro"
  - queries_used_this_period: number
  - queries_limit: number (500 for nat, 999999 for nat_pro)
  - billing_period_start: timestamp
  - admin_email: string
  - nb_connected: boolean
  - nb_token_expires_at: timestamp
  - nb_needs_reauth: boolean
  - created_at: timestamp
  - updated_at: timestamp
```

### UsersTable (DynamoDB)
Stores individual user data for audit logging and rate limiting.

```yaml
PK: user_id
Attributes:
  - user_id: string (PK)
  - nation_slug: string (GSI)
  - email: string (GSI)
  - last_query_at: timestamp (for rate limiting)
  - created_at: timestamp
  - last_active_at: timestamp
```

### TenantsTable (DynamoDB)
**Deprecated** - Kept for backwards compatibility during migration.

## 2. OAuth Flow

### Token Storage (Per-Nation)

Tokens are stored in AWS Secrets Manager with the path:
```
nat/nation/{nation_slug}/nb-tokens
```

**Token Data:**
```json
{
  "access_token": "...",
  "refresh_token": "...",
  "expires_at": 1234567890,
  "nation_slug": "yournation",
  "updated_at": "2026-01-13T17:00:00Z"
}
```

### OAuth Callback Flow

1. User initiates OAuth with NationBuilder
2. OAuth callback receives authorization code
3. Code is exchanged for access/refresh tokens
4. Tokens are stored per-nation (not per-user)
5. Nation connection status is updated
6. User is linked to nation via nation_slug

**Key Functions:**
- `store_nb_tokens()` - Stores tokens per nation
- `update_nation_nb_status()` - Updates nation connection status
- `update_user_nation_link()` - Links user to nation

## 3. Usage Tracking

### Per-Nation Query Tracking

Usage is tracked at the nation level, not user level. This allows all team members to share a query pool.

**Key Functions:**
- `track_query_usage_nation(user_id, nation_slug)` - Increments nation query counter
- `increment_query_count_nation(nation_slug)` - Atomic increment operation
- `check_and_reset_billing_cycle_nation(nation_slug)` - Resets counter on new billing period

### Rate Limiting

Rate limiting is still enforced per-user (5-second cooldown) to prevent abuse, but query counting is per-nation.

## 4. Subscription Verification

### Middleware

`NationSubscriptionMiddleware` verifies that:
1. Request includes valid nation_slug
2. Nation has an active subscription (status: "active" or "trialing")
3. Nation hasn't exceeded query limits

**Key Functions:**
- `verify_nation_subscription(user_id, nation_slug)` - Checks subscription status
- `get_nation_subscription(nation_slug)` - Fetches nation record
- `extract_nation_from_headers(headers)` - Extracts nation_slug from headers

**Required Headers:**
- `X-Nat-User-Id` - For rate limiting and audit logging
- `X-Nat-Nation-Slug` - For subscription verification

## 5. Stripe Integration

### Webhook Events

**checkout.session.completed**
- Creates or updates nation record
- Requires `nation_slug` in metadata
- Sets initial subscription status

**customer.subscription.updated**
- Updates nation subscription status/plan
- Resets query counter on billing period change
- Updates query limits based on plan

**customer.subscription.deleted**
- Marks nation subscription as cancelled
- Nation members lose access to Nat

### Checkout Flow

1. User provides `nation_slug` and `plan` (nat/nat_pro)
2. Checkout session created with nation_slug in metadata
3. Stripe redirects to hosted checkout page
4. On success, webhook updates nation record

## 6. Agent Query Flow

### Request Flow

```
Extension → Lambda Function URL → process_streaming_request()
  ↓
Headers: X-Nat-User-Id, X-Nat-Nation-Slug
  ↓
1. Verify nation subscription (active? within limits?)
2. Check user rate limit (5-second cooldown)
3. Get nation tokens from Secrets Manager
4. Execute Claude agent with NationBuilder tools
5. Track usage per nation
6. Return SSE stream to client
```

### Key Handler Functions

- `get_nb_tokens_by_nation(nation_slug)` - Retrieves nation tokens
- `process_streaming_request(body)` - Processes queries with nation context
- `stream_agent_response(...)` - Streams Claude responses via SSE

## 7. Extension Integration

### Required Changes (To Be Implemented)

The browser extension needs to:

1. **Detect Nation Slug from URL**
   ```typescript
   // Extract from: https://{slug}.nationbuilder.com/*
   const nation_slug = extractNationSlugFromUrl(window.location.href);
   ```

2. **Send Nation Slug in API Requests**
   ```typescript
   headers: {
     'X-Nat-User-Id': userId,
     'X-Nat-Nation-Slug': nationSlug,
   }
   ```

3. **Check Nation Subscription Status**
   ```typescript
   // Call API to check if nation has active subscription
   // Show "Subscribe your nation" CTA if not subscribed
   ```

## 8. Migration Strategy

### Backwards Compatibility

All new functions have backwards-compatible equivalents:

| New Function | Legacy Function |
|--------------|----------------|
| `get_nb_tokens_by_nation()` | `get_nb_tokens()` |
| `track_query_usage_nation()` | `track_query_usage()` |
| `check_and_reset_billing_cycle_nation()` | `check_and_reset_billing_cycle()` |
| `verify_nation_subscription()` | `verify_subscription()` |

### Existing User Migration

1. Map user subscriptions to their primary nation
2. Create nation records with current plan
3. Store nation tokens from user tokens
4. Maintain both paths for 6-month transition period

## 9. Testing

### Unit Tests (To Be Updated)

Key test files to update:
- `test_nb_oauth_callback.py` - OAuth with nation tokens
- `test_usage_tracking.py` - Nation-based usage tracking
- `test_subscription_middleware.py` - Nation subscription verification
- `test_stripe_webhook.py` - Nation-level webhooks
- `test_stripe_checkout.py` - Checkout with nation_slug
- `test_nat_agent_streaming.py` - Streaming with nation tokens

### Integration Testing

Test scenarios:
1. New nation subscribes via Stripe → tokens stored per nation
2. Multiple users from same nation → share query pool
3. Query limit reached → all users blocked
4. Subscription cancelled → all users lose access
5. OAuth connects nation → all future users can access

## 10. Key Insights

### Why Per-Nation?

1. **Aligned with NationBuilder** - NB sells to organizations, not individuals
2. **Simpler for customers** - No seat management, no "who pays?" questions
3. **Better pricing** - $29/mo is less than NationBuilder itself
4. **Team collaboration** - Everyone on the team can use Nat

### Security Model

- **Rate limiting** per user prevents abuse
- **Tokens** stored per nation allow team access
- **Query limits** enforced per nation encourage upgrade
- **Subscription checks** happen on every API call

### Scalability

- Nation-based model scales to unlimited team size
- No per-seat billing complexity
- Simpler to track and enforce limits
- Better analytics at organization level

## 11. Future Enhancements

- Multi-nation support for consultants/agencies
- Usage analytics dashboard per nation
- BYOK (Bring Your Own Key) for enterprise
- Admin portal for nation billing management
- Role-based access control within nations

---

# Claude API Integration & Prompt Caching

This section describes how Nat uses the Claude API and implements prompt caching to reduce costs.

## Model

Nat uses **Claude Haiku 4.5** (`claude-haiku-4-5-20251001`) as the default model. This model was chosen for:
- Fast response times (ideal for real-time chat)
- Cost efficiency ($1/$5 per million input/output tokens)
- Support for prompt caching
- 200K token context window
- Strong tool use capabilities

## Prompt Caching Architecture

### Overview

Prompt caching allows Anthropic to cache large, static portions of prompts, reducing both cost and latency. Cached content costs 90% less (10% of base price) to reuse.

**Cost Breakdown:**
- Base input: $1.00 per million tokens
- Cache write: $1.25 per million tokens (25% premium, first time only)
- Cache read: $0.10 per million tokens (90% discount, subsequent uses)

### Cacheable Content

Nat's prompts contain approximately **19,000 tokens** of static content that is cached:

1. **System Prompt** (~4,000 tokens) - `src/nat/agent.py` lines 25-113
   - Assistant personality and guidelines
   - Capability descriptions
   - JSON:API format documentation
   - Usage examples

2. **Tool Schemas** (~15,000 tokens) - Automatically generated from `src/nat/tools.py`
   - 66 NationBuilder API tools
   - Input/output schemas for each tool
   - Tool descriptions and parameters

### Dynamic Content (Not Cached)

The following content changes per query and is NOT cached:
- User's query text
- Page context (if provided by extension)
- Conversation history (in multi-turn sessions)

### Cost Savings

**Per-query cost analysis:**

*Without caching:*
- Static content: 19,000 tokens × $1.00/1M = $0.019
- Dynamic content: ~500 tokens × $1.00/1M = $0.0005
- **Total per query: ~$0.019**

*With caching (after first query):*
- Cache read: 19,000 tokens × $0.10/1M = $0.0019
- Dynamic content: ~500 tokens × $1.00/1M = $0.0005
- **Total per query: ~$0.0024**

**Savings: 87% reduction** on cached portions (~$0.017 saved per query)

For a user session with 10 queries:
- Without caching: $0.19
- With caching: $0.043 (first query $0.021 + 9 × $0.0024)
- **Total savings: $0.147 (77%)**

### Implementation

Prompt caching is enabled in `src/nat/agent.py` via the `create_nat_options()` function:

```python
def create_nat_options(slug, token, model, enable_caching=True):
    if enable_caching:
        _setup_prompt_caching()
    # ... rest of setup
```

The `_setup_prompt_caching()` function sets the `ANTHROPIC_BETA` environment variable to enable the prompt caching beta feature:

```python
os.environ["ANTHROPIC_BETA"] = "prompt-caching-2024-07-31"
```

This environment variable is respected by the underlying Anthropic API client used by the Claude Agent SDK.

### Cache Lifetime

- **Default TTL:** 5 minutes
- **Extended TTL:** Up to 1 hour (at additional cost)

For typical user sessions, the 5-minute cache is sufficient as users often send multiple queries within that window.

### Disabling Caching

To disable prompt caching (e.g., for testing):

```bash
export NAT_DISABLE_PROMPT_CACHING=true
```

Or pass `enable_caching=False` to `create_nat_options()`.

## Monitoring Cache Performance

### Environment Variables

The Anthropic API returns cache usage metrics in response headers:
- `anthropic-cache-creation-input-tokens` - Tokens written to cache
- `anthropic-cache-read-input-tokens` - Tokens read from cache

These metrics should be logged in production to verify caching effectiveness.

### Logging

The agent logs caching status at INFO level:
```
INFO: Enabled prompt caching: ANTHROPIC_BETA=prompt-caching-2024-07-31
```

### Future Enhancements

To fully leverage cache metrics:

1. Parse API response headers in Lambda handlers
2. Log cache hit/miss rates to CloudWatch
3. Track cost savings in usage analytics
4. Alert if cache hit rate drops below threshold

## SDK Support Status

As of January 2026:
- **Claude Agent SDK version:** 0.1.19
- **Native caching support:** Not yet implemented in SDK
- **Workaround:** Using `ANTHROPIC_BETA` environment variable

The current implementation uses environment variables as a forward-compatible approach. When the SDK adds native support for prompt caching configuration, we can migrate to using SDK-provided options.

## Best Practices

1. **Keep static content first** - Place cacheable content (system prompt, tool schemas) before dynamic content
2. **Minimize prompt changes** - Don't modify the system prompt between queries
3. **Use consistent formatting** - Even small changes to cached content invalidate the cache
4. **Monitor cache hits** - Track metrics to ensure caching is working
5. **Test without cache** - Periodically verify functionality without caching

## References

- [Anthropic Prompt Caching Documentation](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
- [Claude Haiku 4.5 Pricing](https://www.anthropic.com/claude/pricing)
- [Claude Agent SDK](https://github.com/anthropics/anthropic-sdk-python)

## Related Files

- `src/nat/agent.py` - Agent configuration and caching setup
- `src/nat/tools.py` - Tool definitions (generates cached schemas)
- `src/lambdas/nat_agent_streaming/handler.py` - Streaming Lambda handler
- `src/lambdas/nat_agent/handler.py` - Non-streaming Lambda handler
