# Test Credentials — Scholar

## Admin / Reviewer account
- Email: `ryannazha@gmail.com`
- Password: `Test1234!`
- Role: **Admin** (matches `OWNER_EMAIL` env var → unlocks `/admin/orders` and admin endpoints)

## Student test accounts
No fixed seed. Register dynamically with any unique email + password ≥ 6 chars.

## Stripe
Uses `STRIPE_API_KEY=sk_test_emergent` (pre-configured test key). Test card `4242 4242 4242 4242`, any future expiry, any 3-digit CVC.

## AI Generation
`EMERGENT_LLM_KEY` (pre-configured). Model: `openai/gpt-5.2`.

## Email
Resend API key configured (`re_G4se9ug1_...`). Sending FROM `onboarding@resend.dev`.
**Note:** Resend test mode only allows sending TO `ryannazha@gmail.com`. Verify a domain at resend.com/domains to send to actual student emails.

## Bypass Stripe in backend tests
```js
db.assignments.updateOne({id:'<assignment_id>'}, {$set:{status:'paid'}})
db.ai_check_orders.updateOne({id:'<order_id>'}, {$set:{status:'paid'}})
```
