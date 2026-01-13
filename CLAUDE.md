# Claude API Integration & Prompt Caching

This document describes how Nat uses the Claude API and implements prompt caching to reduce costs.

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
