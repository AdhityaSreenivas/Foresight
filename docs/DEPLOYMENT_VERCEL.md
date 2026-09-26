# Foresight — Vercel Production Deployment Guide

**Project:** Foresight  
**Team:** Team Oblivion  
**Primary Target:** Vercel (Web Application & Static Assets)  
**External Services:** Managed PostgreSQL, Managed Redis, Persistent Celery Worker  

---

## 1. Architectural Overview

Foresight is deployed following a decoupled cloud-native architecture:

```
                          ┌──────────────────────────┐
                          │          VERCEL          │
                          │   Django WSGI Frontend   │
                          │   & Static Assets (CDN)  │
                          └─────────────┬────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
                    ▼                   ▼                   ▼
         ┌─────────────────────┐ ┌─────────────┐ ┌─────────────────────┐
         │ Managed PostgreSQL  │ │ Managed     │ │  Persistent Worker  │
         │ (Neon/Supabase/RDS) │ │ Redis Cloud │ │ (Celery + PyTorch)  │
         │   PostgreSQL 15+    │ │  Upstash    │ │   Render/Railway    │
         └──────────▲──────────┘ └──────┬──────┘ └──────────▲──────────┘
                    │                   │                   │
                    └───────────────────┴───────────────────┘
```

- **Vercel**: Serves the unified Django web application (all HTML templates, HTMX endpoints, REST API routes, and static assets) via serverless WSGI execution.
- **External PostgreSQL**: High-performance persistent database (PostgreSQL 15+) using `psycopg 3` and connection pooling (`CONN_MAX_AGE=60`).
- **External Redis**: Low-latency message broker and result backend for Celery background tasks, and distributed cache for Django.
- **External Celery Worker**: Persistent background compute service executing heavy dataset ingestion, DistilBERT embeddings, and asynchronous training jobs without serverless execution timeout limits.

---

## 2. Prerequisites & Cloud Accounts

1. **Vercel Account:** Pro or Team account recommended for function timeouts > 15s.
2. **Managed PostgreSQL:** Neon, Supabase, AWS RDS, or Railway PostgreSQL instance (PostgreSQL 15+).
3. **Managed Redis:** Redis Cloud, Upstash Redis, or AWS ElastiCache.
4. **Persistent Worker Host:** Render, Railway, DigitalOcean App Platform, or AWS ECS/EC2 to run `celery -A config worker`.

---

## 3. Deployment Configuration Files

The codebase includes all necessary deployment descriptors:

- `vercel.json`: Defines `@vercel/python` WSGI build for `config/wsgi.py`, static asset build for `build_files.sh`, and routing rules.
- `build_files.sh`: Installs Python dependencies and executes `python manage.py collectstatic --noinput`.
- `.python-version`: Pins Python version to `3.12` for cloud build environments.
- `config/wsgi.py`: Exports `app = application` WSGI interface and defaults `DJANGO_SETTINGS_MODULE` to `config.settings.prod`.
- `config/settings/prod.py`: Production security configuration (HSTS, SSL redirect, secure cookies, proxy headers).

---

## 4. Required Environment Variables

Configure these environment variables in your Vercel Project Settings (**Settings → Environment Variables**):

| Variable | Description | Example / Recommended Value |
| :--- | :--- | :--- |
| `DJANGO_SETTINGS_MODULE` | Active Django settings module | `config.settings.prod` |
| `SECRET_KEY` | Cryptographic signing key (50+ random chars) | `v3ry-s3cur3-r4nd0m-pr0duct10n-k3y-...` |
| `DEBUG` | Debug mode (must be False in production) | `False` |
| `ALLOWED_HOSTS` | Comma-separated list of allowed hostnames | `.vercel.app,foresight.yourdomain.com` |
| `CSRF_TRUSTED_ORIGINS` | Trusted origins for CSRF verification | `https://*.vercel.app,https://foresight.yourdomain.com` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@ep-cool-db.us-east-2.neon.tech/psif?sslmode=require` |
| `REDIS_URL` | Redis cache connection string | `rediss://default:token@cool-redis.upstash.io:6379` |
| `CELERY_BROKER_URL` | Celery broker URL | `rediss://default:token@cool-redis.upstash.io:6379/0` |
| `CELERY_RESULT_BACKEND`| Celery task result backend | `rediss://default:token@cool-redis.upstash.io:6379/1` |
| `SECURE_SSL_REDIRECT` | Force SSL redirects | `True` |
| `SECURE_HSTS_SECONDS` | HSTS max-age header | `31536000` |

---

## 5. Step-by-Step Vercel Deployment

### Method A: Deploy via Vercel CLI

1. Install Vercel CLI globally:
   ```bash
   npm install -g vercel
   ```

2. Log in to Vercel:
   ```bash
   vercel login
   ```

3. Link and Deploy Project:
   ```bash
   # From the project root
   vercel link
   vercel env pull .env.production.local # optional: pull existing config
   vercel --prod
   ```

### Method B: Deploy via GitHub / GitLab Integration

1. Push repository to your Git provider (GitHub / GitLab).
2. In the Vercel Dashboard, click **Add New... → Project**.
3. Import the `prototype_165` (Foresight) repository.
4. Select **Other** as the Framework Preset.
5. In **Environment Variables**, add all required variables listed in Section 4.
6. Click **Deploy**.

---

## 6. External Celery Worker Setup

In accordance with **Critical Celery / Redis Rule (Section 9)**, do NOT attempt to run Celery inside Vercel serverless request handlers.

To deploy the worker on Render, Railway, or AWS:

1. **Build Command:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Start Command:**
   ```bash
   celery -A config worker --loglevel=info --concurrency=2 -P solo
   ```

3. **Required Environment Variables:**
   Share the exact same `DATABASE_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, and `DJANGO_SETTINGS_MODULE=config.settings.prod`.

---

## 7. Post-Deployment Verification

1. **Health Check:**
   Access `https://your-deployment.vercel.app/health/`.
   Expected response:
   ```json
   {
     "status": "healthy",
     "database": "ok",
     "cache": "ok"
   }
   ```

2. **Static Asset Verification:**
   Verify CSS/JS loads correctly by inspecting `https://your-deployment.vercel.app/static/css/main.css` (HTTP 200).

3. **Admin Flow Demo Verification:**
   Log in with demo credentials at `https://your-deployment.vercel.app/accounts/login/` and confirm access to the Admin Flow dashboard.
