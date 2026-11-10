# DIGITAL STORE PRO — Python / React / TypeScript / Rust

A real, source-available **integrated development build** of a digital-products store with two independent React + TypeScript/Vite apps, a FastAPI + SQLAlchemy + Alembic API, and a PyO3/maturin Rust extension for validating and deduplicating digital keys.

> **Release status: core MVP, not certified production-ready.** Order placement, manually verified payments, encrypted digital-code fulfillment, and product/admin workflows are implemented and covered by backend tests. Not all features in the original master specification are implemented: see `STATUS_AND_SECURITY.md`. Do not accept real payments before completing the production checklist.

## Repository layout

```text
DIGITAL_STORE_PRO/
├── backend/
│   ├── .env.example
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/versions/305bacc3fafb_initial_schema.py
│   └── app/
│       ├── main.py              # FastAPI app and middleware
│       ├── api/                 # installation, auth, products, checkout, admin
│       ├── core/                # configuration, ORM sessions, security
│       ├── models/              # 36 SQLAlchemy tables
│       ├── schemas/             # Pydantic request validation
│       └── services/            # server-side pricing + digital fulfillment
├── frontend/
│   ├── store/                   # standalone React/Vite storefront
│   └── admin/                   # standalone React/Vite admin + installation wizard
├── rust/digital_core/          # PyO3 native module, Rust unit tests
├── tests/                      # FastAPI TestClient + SQLite test suite
├── deploy/                     # Nginx + systemd examples
├── INSTALL.md                  # Arabic instructions, beginning from zero
└── STATUS_AND_SECURITY.md      # implemented / pending / threat model
```

**Backend is NOT deployed to Cloudflare Pages**. The static React apps can be hosted on separate Cloudflare Pages projects. FastAPI + Rust + PostgreSQL run on an ASGI-capable server, VPS or compatible container platform.

## First run

Read **[INSTALL.md](INSTALL.md)** for the complete commands (Python venv, Rust build, PostgreSQL, Alembic, frontend, first admin account, VPS and Cloudflare Pages).

From a correctly configured backend virtualenv:

```bash
cd backend
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

From separate terminals:

```bash
cd frontend/store && npm install && npm run dev
cd frontend/admin && npm install && npm run dev
```

Open **http://localhost:5174** for the first installation wizard, then sign in and enable a valid Bank Transfer or Cash Plus payment method before taking orders.

## Trust boundaries

- **Frontend** is untrusted. Checkout re-reads products and computes totals using `Decimal` in the Python API.
- **Admin** sessions are opaque random database-backed cookies (`HttpOnly`, `SameSite=Lax`; `Secure` required in production). Mutations require CSRF header.
- **Passwords** are Argon2id hashes, never plaintext or pre-populated credentials.
- **Payments** start unverified. Only super-admin confirmation of a manual payment performs fulfillment; PayPal/card are disabled until official gateways are implemented.
- **Digital codes** are Fernet-encrypted at rest, validated/keyed-fingerprinted by the Rust module. A PostgreSQL `FOR UPDATE SKIP LOCKED` transaction plus a unique allocation constraint prevents overlapping assignments.
- **Order-access secret** is random, stored hashed in the database, returned only on checkout, required for guest order details. The browser keeps the receipt locally; losing it without a registered account prevents recovery in this build.
- **Rust** is required at runtime for digital-code imports and paid-code assignment. No silent validation fallback is used in normal operation.

## Test status (environment at creation)

- `pytest tests -q`: **7 passed** (initial installation/login/CSRF, product checkout, expired and active discounts, instant-code allocation/idempotency, encrypted manual delivery).
- `alembic upgrade head`: **passed on SQLite development database**.
- Python imports and FastAPI route generation: **passed**.
- TSX syntactic parse/transpile of both React entrypoints: **passed** (global TypeScript compiler).
- `npm install` failed due unavailable npm registry DNS in this environment, so **full typechecking/Vite builds and UI E2E have not been executed**.
- Rust compiler / cargo / maturin were unavailable, so **cargo test and native module build have not been executed**. Rust integration was tested using a stub, not a compiled native extension.
- PostgreSQL integration/concurrency tests, payment gateway sandbox tests, and live deployments: **not executed**.

See `STATUS_AND_SECURITY.md` for all limitations and next phases.

## Sources for deployment/build setup

- [Maturin native Python extension workflow](https://www.maturin.rs/tutorial.html)
- [Cloudflare Pages React deployment](https://developers.cloudflare.com/pages/framework-guides/deploy-a-react-site/)
- [FastAPI deployment](https://fastapi.tiangolo.com/deployment/)
