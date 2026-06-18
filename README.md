# FastAPI JWT Authentication & Franchise Management System

A production-ready FastAPI backend featuring JWT auth, franchise CRUD, OTP verification, Redis caching, and WebSocket notifications.

---

## Features

| Feature | Details |
|---|---|
| **Single Login API** | Unified endpoint for Super Admin and Franchise |
| **JWT Auth** | Access + Refresh tokens with role claims |
| **Franchise CRUD** | Create, Read, Update, Delete with pagination & search |
| **OTP** | Email via SMTP or SMS via Twilio (5-min expiry) |
| **Redis Cache** | OTP storage, token blacklist, franchise data cache |
| **WebSocket** | Real-time notifications at `/ws/notifications` |
| **Role-Based Access** | Super Admin vs Franchise permissions |
| **Security** | bcrypt passwords, CORS, secure headers, token blacklist |
| **ORM** | SQLAlchemy 2.0 async with Alembic migrations |
| **Database** | PostgreSQL (async via asyncpg) |

---

## Project Structure

```
fastapi_project/
├── app/
│   ├── main.py                  # App factory, middleware, lifespan
│   ├── core/
│   │   ├── config.py            # Pydantic settings from .env
│   │   ├── database.py          # Async SQLAlchemy engine + session
│   │   └── security.py          # bcrypt + OAuth2 scheme
│   ├── models/
│   │   ├── user.py              # User ORM model (super_admin | franchise)
│   │   └── franchise.py         # Franchise ORM model
│   ├── schemas/
│   │   ├── auth.py              # Login, Token, OTP schemas
│   │   ├── user.py              # User create/update/response
│   │   └── franchise.py         # Franchise create/update/response
│   ├── routes/
│   │   ├── auth.py              # /api/v1/auth/*
│   │   ├── franchise.py         # /api/v1/franchise/*
│   │   ├── profile.py           # /api/v1/profile
│   │   └── websocket.py         # /ws/notifications
│   ├── services/
│   │   ├── auth_service.py      # Login logic
│   │   ├── franchise_service.py # Franchise business logic
│   │   └── otp_service.py       # OTP generation & verification
│   ├── utils/
│   │   ├── jwt.py               # Token creation & decoding
│   │   ├── otp.py               # OTP generator
│   │   ├── redis.py             # Redis helpers (OTP, cache, blacklist)
│   │   ├── smtp.py              # Email OTP via SMTP
│   │   └── twilio.py            # SMS OTP via Twilio
│   ├── middleware/
│   │   └── auth_middleware.py   # Request logging + security headers
│   ├── dependencies/
│   │   └── role_checker.py      # JWT → User, role enforcement
│   └── tests/
│       └── test_auth.py         # Pytest async tests
├── alembic/                     # Database migrations
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 0001_initial.py
├── alembic.ini
├── requirements.txt
├── .env                         # Copy of .env.example with dev defaults
└── .env.example
```

---

## Quick Start

### 1. Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Redis 7+

### 2. Clone & Install

```bash
git clone <repo-url>
cd fastapi_project
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your database URL, SMTP credentials, etc.
```

### 4. Run Database Migrations

```bash
alembic upgrade head
```

### 5. Start the Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The server auto-creates the **Super Admin** user on first startup using `.env` credentials.

Visit **http://localhost:8000/docs** for the interactive Swagger UI.

---

## API Reference

### Authentication

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/auth/login` | ❌ | Login (Super Admin or Franchise) |
| POST | `/api/v1/auth/refresh` | ❌ | Refresh access token |
| POST | `/api/v1/auth/logout` | ✅ | Blacklist current token |
| POST | `/api/v1/auth/send-otp` | ❌ | Send OTP via email or SMS |
| POST | `/api/v1/auth/verify-otp` | ❌ | Verify OTP |

#### Super Admin Login
```json
POST /api/v1/auth/login
{
  "email": "admin@example.com",
  "password": "Admin@1234"
}
```

#### Franchise Login
```json
POST /api/v1/auth/login
{
  "email": "franchise@example.com",
  "password": "secret",
  "franchise_code": "FRAN-001"
}
```

#### Response
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "role": "super_admin"
}
```

---

### Franchise CRUD

| Method | Endpoint | Auth | Role |
|--------|----------|------|------|
| POST | `/api/v1/franchise` | ✅ | Super Admin |
| GET | `/api/v1/franchise?search=kochi&page=1&limit=10` | ✅ | Any |
| GET | `/api/v1/franchise/{id}` | ✅ | Any |
| PUT | `/api/v1/franchise/{id}` | ✅ | Super Admin |
| DELETE | `/api/v1/franchise/{id}` | ✅ | Super Admin |

#### Create Franchise
```json
POST /api/v1/franchise
Authorization: Bearer <token>

{
  "name": "Kochi Branch",
  "email": "kochi@franchise.com",
  "password": "Secret@123",
  "phone": "+919876543210",
  "address": "MG Road, Kochi, Kerala",
  "franchise_code": "FRAN-KOCHI-001"
}
```

---

### Profile

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/v1/profile` | ✅ | Get own profile |
| PUT | `/api/v1/profile` | ✅ | Update own profile |

---

### OTP

```json
POST /api/v1/auth/send-otp
{
  "email": "user@example.com",
  "purpose": "login"
}

POST /api/v1/auth/verify-otp
{
  "identifier": "user@example.com",
  "otp": "482910",
  "purpose": "login"
}
```

**Purposes:** `login` | `password_reset` | `franchise_auth`

OTP expires in **5 minutes** (configurable via `OTP_EXPIRE_MINUTES`).

---

### WebSocket

Connect at: `ws://localhost:8000/ws/notifications?token=<access_token>`

#### Client → Server Events
```json
{"type": "ping"}
{"type": "subscribe", "topic": "franchise_updates"}
{"type": "broadcast", "data": {"message": "Hello all"}}  // Super Admin only
```

#### Server → Client Events
```json
{"type": "connected",    "data": {"message": "...", "user_id": "...", "total_online": 3}, "timestamp": "..."}
{"type": "pong",         "data": {"status": "ok"}, "timestamp": "..."}
{"type": "subscribed",   "data": {"topic": "franchise_updates"}, "timestamp": "..."}
{"type": "system_update","data": {...}, "timestamp": "..."}
```

---

## Running Tests

```bash
pip install pytest pytest-asyncio
pytest app/tests/ -v
```

---

## Nginx + Gunicorn (Production)

```bash
# Install
pip install gunicorn

# Run with multiple workers
gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker \
  --workers 4 \
  --bind 0.0.0.0:8000

# Nginx config snippet
server {
    listen 80;
    server_name api.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket support
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

---

## Security Notes

- Change `SECRET_KEY` in production to a long random string
- Use a strong `SUPER_ADMIN_PASSWORD`
- Enable HTTPS in production (Let's Encrypt / AWS ACM)
- Set `DEBUG=False` in production
- Restrict `ALLOWED_ORIGINS` to your frontend domain
# test
# pipeline test 2
# t3.small test
