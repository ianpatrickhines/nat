# Implementation Summary: Per-Nation Billing Model

## Status: Backend Complete ✅

The backend infrastructure has been fully rearchitected to support nation-based (organization-level) billing instead of individual user subscriptions.

## What Was Implemented

### Core Infrastructure (Complete)

**1. Database Schema** ✅
- Created `NationsTable` with nation_slug as primary key
- Stores subscription status, plan, usage, and billing info per nation
- Updated `UsersTable` to link users to nations
- Added IAM policies and environment variables

**2. OAuth Flow** ✅
- Tokens now stored per-nation: `nat/nation/{slug}/nb-tokens`
- Nation connection status tracked in NationsTable
- Users linked to nations via nation_slug

**3. Usage Tracking** ✅
- Queries counted per nation (not per user)
- Nation-level billing cycle resets
- Per-user rate limiting for abuse prevention

**4. Subscription Verification** ✅
- New middleware checks nation subscription status
- Enforces query limits per nation (0 = unlimited)
- Requires `X-Nat-Nation-Slug` header in API requests

**5. Stripe Integration** ✅
- Webhooks handle nation-level subscriptions
- Checkout requires nation_slug in metadata
- New pricing: nat ($29/mo, 500 queries), nat_pro ($79/mo, unlimited)

**6. Lambda Handlers** ✅
- Streaming handler uses nation tokens
- Usage tracking per nation
- Query context includes nation_slug

**7. Documentation** ✅
- Comprehensive CLAUDE.md with architecture details
- Data models, flows, and integration points documented

## What Needs to Be Done

### 1. Extension Updates (Phase 5)

**Required Changes:**

```typescript
// src/background/index.ts

// 1. Detect nation_slug from URL
function extractNationSlugFromUrl(url: string): string | null {
  const match = url.match(/https?:\/\/([^.]+)\.nationbuilder\.com/);
  return match ? match[1] : null;
}

// 2. Update auth state to include nation_slug
interface AuthState {
  isAuthenticated: boolean;
  userId: string | null;
  nationSlug: string | null;  // NEW
  subscriptionStatus: 'active' | 'trialing' | 'cancelled' | null;
}

// 3. Send nation_slug in API requests
const response = await fetch(STREAMING_URL, {
  method: 'POST',
  headers: {
    'X-Nat-User-Id': authState.userId || '',
    'X-Nat-Nation-Slug': authState.nationSlug || '',  // NEW
  },
  body: JSON.stringify({
    query: request.query,
    user_id: authState.userId,
    nation_slug: authState.nationSlug,  // NEW
    context: request.context || {},
  }),
});

// 4. Check nation subscription instead of user subscription
async function checkNationSubscription(nationSlug: string) {
  // Call API to verify nation has active subscription
  // Show "Subscribe your nation" CTA if not subscribed
}
```

**Files to Update:**
- `extension/src/background/index.ts`
- `extension/src/content/index.tsx` (if applicable)
- `extension/src/utils/auth.ts` (if exists)

### 2. Test Suite Updates (Phase 9)

**Files to Update:**

1. **test_nb_oauth_callback.py**
   - Test nation token storage
   - Test nation connection status updates
   - Test user-to-nation linking

2. **test_usage_tracking.py**
   - Test `track_query_usage_nation()`
   - Test `increment_query_count_nation()`
   - Test `check_and_reset_billing_cycle_nation()`
   - Test nation-level counters

3. **test_subscription_middleware.py**
   - Test `NationSubscriptionMiddleware`
   - Test `verify_nation_subscription()`
   - Test nation_slug extraction from headers
   - Test unlimited plan (queries_limit = 0)

4. **test_stripe_webhook.py**
   - Test nation creation/update on checkout
   - Test subscription updates for nations
   - Test metadata with nation_slug

5. **test_stripe_checkout.py**
   - Test checkout with nation_slug parameter
   - Test metadata includes nation_slug
   - Test new pricing (nat/nat_pro)

6. **test_nat_agent_streaming.py**
   - Test `get_nb_tokens_by_nation()`
   - Test streaming with nation_slug
   - Test nation usage tracking

### 3. Deployment Steps

**Infrastructure Deployment:**

```bash
# 1. Deploy CloudFormation stack updates
aws cloudformation update-stack \
  --stack-name nat-infrastructure-dev \
  --template-body file://infrastructure/template.yaml \
  --parameters ParameterKey=Environment,ParameterValue=dev \
  --capabilities CAPABILITY_NAMED_IAM

# 2. Wait for stack update to complete
aws cloudformation wait stack-update-complete \
  --stack-name nat-infrastructure-dev

# 3. Verify NationsTable was created
aws dynamodb describe-table --table-name nat-nations-dev
```

**Lambda Deployment:**

```bash
# Deploy updated Lambda functions
./tasks/deploy_lambdas.sh dev
```

### 4. Migration Strategy

**Existing Users → Nations:**

```python
# Migration script (pseudo-code)
def migrate_users_to_nations():
    users_table = dynamodb.Table('nat-users-prod')
    tenants_table = dynamodb.Table('nat-tenants-prod')
    nations_table = dynamodb.Table('nat-nations-prod')
    
    # 1. Get all active users
    users = users_table.scan()
    
    for user in users['Items']:
        tenant_id = user.get('tenant_id')
        if not tenant_id:
            continue
            
        # 2. Get tenant info
        tenant = tenants_table.get_item(Key={'tenant_id': tenant_id})['Item']
        
        # 3. Extract nation_slug from user's NB connection
        nb_slug = user.get('nb_slug') or extract_from_tokens(user['user_id'])
        
        if not nb_slug:
            continue
        
        # 4. Create or update nation record
        nation_item = {
            'nation_slug': nb_slug,
            'stripe_customer_id': tenant.get('stripe_customer_id'),
            'stripe_subscription_id': tenant.get('stripe_subscription_id'),
            'subscription_status': tenant.get('stripe_subscription_status'),
            'subscription_plan': tenant.get('plan'),
            'queries_used_this_period': tenant.get('queries_this_month', 0),
            'queries_limit': tenant.get('queries_limit', 500),
            'admin_email': user.get('email'),
            # ... other fields
        }
        nations_table.put_item(Item=nation_item)
        
        # 5. Update user to link to nation
        users_table.update_item(
            Key={'user_id': user['user_id']},
            UpdateExpression='SET nation_slug = :slug',
            ExpressionAttributeValues={':slug': nb_slug}
        )
        
        # 6. Migrate tokens from user to nation
        migrate_tokens(user['user_id'], nb_slug)
```

### 5. Rollout Plan

**Phase 1: Soft Launch (Week 1)**
- Deploy infrastructure changes
- Run migration script for existing users
- Monitor error rates and usage patterns
- Keep both old and new code paths active

**Phase 2: Extension Update (Week 2)**
- Deploy updated extension with nation_slug detection
- Beta test with select nations
- Monitor Sentry/CloudWatch for errors

**Phase 3: Full Launch (Week 3)**
- Update pricing page
- Send email to existing users
- Announce new pricing model
- Monitor customer feedback

**Phase 4: Deprecation (Month 6)**
- Remove old per-user code paths
- Clean up deprecated functions
- Archive TenantsTable (keep for records)

## Testing Checklist

Before deploying to production:

- [ ] Infrastructure stack updates successfully
- [ ] NationsTable created with correct schema
- [ ] IAM permissions allow Lambda access to NationsTable
- [ ] OAuth flow creates nation records
- [ ] Tokens stored per-nation in Secrets Manager
- [ ] Usage tracking increments nation counters
- [ ] Subscription middleware blocks inactive nations
- [ ] Stripe webhooks create/update nations
- [ ] Stripe checkout includes nation_slug
- [ ] Streaming handler uses nation tokens
- [ ] Rate limiting still works per-user
- [ ] Extension detects nation_slug from URL
- [ ] Extension sends nation_slug in headers
- [ ] All unit tests pass
- [ ] Integration tests with Stripe sandbox pass
- [ ] Load testing shows acceptable performance

## Monitoring

**Key Metrics to Track:**

```python
# CloudWatch Dashboard metrics
metrics = {
    'NationCreations': 'Count of new nation records created',
    'TokensMigrated': 'Count of tokens migrated from user to nation',
    'SubscriptionVerifications': 'Count of nation subscription checks',
    'QueryLimitErrors': 'Count of query limit exceeded errors',
    'NationNotFoundErrors': 'Count of nation_slug not found errors',
    'AverageQueriesPerNation': 'Average queries used per nation',
    'UnlimitedPlanUsage': 'Queries from nat_pro (unlimited) plans',
}
```

**Alarms to Set:**

1. High error rate on nation subscription checks
2. Spike in "nation not found" errors
3. High number of query limit exceeded errors
4. Stripe webhook processing failures
5. Token migration failures

## Success Criteria

The migration is successful when:

✅ All existing users mapped to nations
✅ New signups create nation subscriptions
✅ Usage tracking accurate per-nation
✅ Query limits enforced correctly (0 = unlimited)
✅ Team members can share nation subscription
✅ Extension works with nation_slug
✅ Stripe integration stable
✅ Error rates < 1%
✅ Customer support tickets minimal
✅ Revenue tracking accurate

## Rollback Plan

If critical issues arise:

1. **Immediate**: Revert Lambda functions to previous version
2. **Quick**: Switch extension back to user-based model
3. **Full**: Rollback infrastructure (keep NationsTable for data)

**Rollback triggers:**
- Error rate > 5%
- Customer complaints > 10/day
- Stripe integration failures
- Data loss or corruption
- Security vulnerability discovered

## Questions/Decisions Needed

1. **Nation slug detection**: How to handle users with access to multiple nations?
   - **Recommendation**: Detect from URL, allow manual selection

2. **Trial period**: How long should trial subscriptions last?
   - **Recommendation**: 14 days, 50 queries

3. **Grandfathering**: Should existing users keep their pricing?
   - **Recommendation**: Yes, for 6 months

4. **Multi-nation users**: Should we support consultants/agencies?
   - **Recommendation**: Phase 2 feature, use nation switching UI

5. **Admin portal**: Do we need a nation admin dashboard?
   - **Recommendation**: Use Stripe Customer Portal for now

## Resources

- [CLAUDE.md](./CLAUDE.md) - Full architecture documentation
- [Infrastructure Template](./infrastructure/template.yaml) - CloudFormation template
- [GitHub Issue](https://github.com/ianpatrickhines/nat/issues/XXX) - Original issue

## Contact

For questions about this implementation:
- Architecture: See CLAUDE.md
- Implementation: Review PR commits
- Deployment: Follow steps in this doc
- Issues: Create GitHub issue

---

**Status as of 2026-01-13:**
- Backend: ✅ Complete
- Extension: ⏳ Pending
- Testing: ⏳ Pending
- Deployment: ⏳ Pending
- Migration: ⏳ Pending
