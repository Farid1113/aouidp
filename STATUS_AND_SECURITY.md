# STATUS & SECURITY — read before accepting real orders

**This is an integrated functional MVP, not a finished production-ready commerce system.** The original specification covers a complete commercial platform; that requires substantially more implementation, infrastructure and compliance work than can be safely represented by a single prototype ZIP.

## Implemented with real endpoints/UI

- Separate Vite/React/TypeScript apps for store and admin, with CSS3 responsive UI, client Dark/Light, initial AR/FR/EN UI strings and RTL support.
- First-install wizard tied to PostgreSQL/SQLite installation table; database-backed installer lock, super-admin chosen by owner, Argon2id credentials (no hardcoded default password).
- Opaque server-side session hashes, HttpOnly cookies, CSRF for authenticated mutations, origin checks, explicit CORS allowlist, admin/super-admin/manager/support role models.
- Category CRUD, product CRUD (archive/hide instead of destroying transactional history), public product catalog/search/category filter, local cart, wishlist, checkout and order status.
- Server-side `Decimal` totals, discounts with real server timestamps, fixed/percentage offers, automatic expiry on checkout; storefront timer and scheduled catalog refetch at offer expiry.
- Bank Transfer and Cash Plus payment method configuration with manual verification, payment reference and a limited private proof upload (JPEG/PNG/PDF, max 2MB). Strong unguessable guest receipt tokens, with hashed reference stored in DB.
- Admin payment confirmation **only by super-admin**. Payment/inventory changes occur in a transaction. Instant code allocation uses PostgreSQL `FOR UPDATE SKIP LOCKED` and `UNIQUE` order-item allocation, idempotent confirmation; encrypted code delivery and server-side protected access.
- Rust digital_core source: PyO3 native module (validation, HMAC-SHA256 fingerprints, masking), consumed by the real backend import/fulfillment paths. Missing native module fails closed, not silently replaced in normal code.
- Manual/service delivery status and encrypted private delivery messages, order CSV export, dashboard reading real orders, private event notification records, public support-ticket creation and admin ticket listing, audit-log viewing.
- 36 SQLAlchemy tables in an initial Alembic migration, including foundation models for referrals, coupons, loyalty and gift cards.

## Not yet complete / do NOT claim ready

- **Visa/Mastercard and PayPal** are **not integrated**. Card/PayPal choices are disabled and cannot be enabled with the current API. No webhook verifier, sandbox tests or real refunds are implemented. Use official hosted providers only after technical/account onboarding.
- **Cash Plus and bank transfers** are manual instructions only, not proof of receipt. No official Cash Plus API integration.
- No true invoicing/report PDF/Excel exporter; only orders CSV is implemented. Gift cards, loyalty points, customer referrals, coupons, bundles, variants, recurring billing, related products, verified reviews, inventory movement for manual products, mass import/export and abandoned carts are database scaffolds / future work.
- UI translations are incomplete; page-level SEO metadata, server rendering, accessibility review, real marketing CMS, cookie consent, full theme editor and legal localization need completion.
- No SMTP email dispatch, WhatsApp Business API, push subscriptions, real-time webhooks, 2FA enrollment or secure automated account recovery. Installer email is stored as recovery contact only; it is not an operational recovery flow.
- Supports manually configured credentials/DB URL via `.env`, **not** editing/creating DB credentials from the browser wizard. This prevents leaking database credentials to the frontend.
- Only coarse role checks are enforced; detailed permission rows exist but are not checked on every endpoint. Extend per-endpoint permission matrix before adding delegated admin accounts.
- Customer order access uses a high-entropy receipt secret saved in browser localStorage; it can be lost when the browser is cleared, and XSS protections/CSP require an independent audit. Guest order recovery by verified email not available.
- Current rate limiter is in-process memory, not shared across workers or nodes. Real production requires centralized edge/Redis/gateway rate limits, log monitoring and incident response.
- Upload files get signature and size checks; add malware scanning, retention rules and object storage before handling untrusted production attachments. Review MIME handling and deploy `private_uploads` outside public web roots.
- Admin and frontend CSS/TSX source was syntax-checked but npm packages were unavailable at generation time; execute `npm ci`/`npm install`, `npm run build`, frontend tests and cross-device E2E before release.
- Cargo/Rust/maturin weren't installed at generation time: native module compilation, `cargo test`, Rust integration on Python 3.12/3.13, and PostgreSQL concurrency stress tests must be executed by the deployer.
- No dynamic provider connector, server-side queue, worker retries, transactional outbox, automated scheduled backups, password reset, observability dashboards, CI/CD, domain/DNS/TLS setup or live-host smoke tests are shipped.
- This source requires security review, dependency audits, privacy/legal policies, disaster recovery, and payment provider sandbox verification before public launch.

## Security model and production checklist

1. Set production PostgreSQL, no public DB port, HTTPS, HttpOnly/Secure cookies, same-site subdomains and strict trusted origins; generate unique secret keys and back them up encrypted.
2. Deploy separate shop/admin static builds from source, and ASGI API+Rust on VPS; never put `.env`, DB backups, `.sqlite`, or uploaded proofs in public static assets.
3. Validate native Rust module build; run tests against a real PostgreSQL DB, including parallel payments for the same last inventory code. SQLite is **not** suitable for inventory locking tests.
4. Configure external rate limiting (gateway/Nginx), security event tracking, fraud mitigation, storage quotas, audit retention and permission policies.
5. Complete legal seller terms, reseller licensing, rights to software/subscriptions, privacy (applicable Moroccan law), refund/consumer rights and data retention.
6. Configure authentic official hosted card/PayPal gateway credentials in a provider-specific environment; verify signed callbacks and implement idempotent webhook handling before enabling anything.
7. Set up verified email for receipts, refund confirmations, secure password reset and code delivery notifications; don't send passwords or raw bank/card data over email/WhatsApp.
8. Perform browser E2E, accessibility, mobile UX, CSP/SRI/security headers, dependency/SCA scans, SAST and penetration assessment of a controlled staging environment.
9. Maintain tested encrypted PostgreSQL backup and restore plus code-key and private-proof backup. Keep rotation/recovery procedures.

## Honest test report

Verified in the build environment: **7 pytest tests passed**, Alembic migration **applied to fresh SQLite**, both main React `.tsx` files parsed/transpiled without syntax errors. Not verified: cargo, native PyO3 wheel, Vite dependency install/full compile, Playwright/UI E2E, PostgreSQL row-lock contention, webhook/Sandbox/Live payment, actual Cloudflare+VPS deployment.
