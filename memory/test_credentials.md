# Test Credentials — Scholar

No fixed seed account. The app uses dynamic email/password registration.

## How to test auth
1. Register via `POST /api/auth/register` with any unique email + password (≥ 6 chars), name.
2. Login at `POST /api/auth/login` with the same email/password.

## Suggested test account (create on first run if needed)
- Email: `tester+scholar@example.com`
- Password: `Test1234!`
- Name: `Scholar Tester`

## Stripe
Uses `STRIPE_API_KEY=sk_test_emergent` (pre-configured test key). Use Stripe test card `4242 4242 4242 4242`, any future expiry, any 3-digit CVC, any ZIP.

## AI Generation
Uses `EMERGENT_LLM_KEY` (pre-configured). Model: `openai/gpt-5.2` via `emergentintegrations`.

## Bypass payment in tests
To skip Stripe in backend tests, mark an assignment paid directly in MongoDB:
```js
db.assignments.updateOne({id:'<assignment_id>'}, {$set:{status:'paid'}})
```
Then `POST /api/assignments/{id}/generate` triggers background generation.
