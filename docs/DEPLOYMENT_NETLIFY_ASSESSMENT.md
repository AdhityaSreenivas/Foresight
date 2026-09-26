# Foresight — Netlify Deployment Assessment

**Project:** Foresight  
**Team:** Team Oblivion  
**Date:** September 2026  
**Status:** Evaluated as Secondary Deployment Target — Architecture Preserved Without Incompatible Restructuring  

---

## 1. Executive Summary

Netlify was systematically assessed as an alternate hosting target for the Foresight application. Under the strict rules of the **Autononous Execution Contract**, no changes to the application architecture, business logic, asynchronous task queues, or persistence semantics are permitted merely to conform to a serverless platform's constraints.

**Verdict:** **Netlify is NOT recommended for the unified Django application without extensive wrapper adaptations.**  
**Vercel provides a much cleaner, direct WSGI-compatible target.**

---

## 2. Technical Comparison: Netlify vs. Vercel for Foresight

| Architectural Feature | Foresight Requirement | Vercel Deployment Target | Netlify Deployment Target |
| :--- | :--- | :--- | :--- |
| **Python Runtime / WSGI** | Python 3.12+ WSGI/ASGI application | Native `@vercel/python` builder runs WSGI `application` directly without third-party wrappers. | Requires AWS Lambda-style handler adaptation (e.g. `serverless-wsgi` or `mangum`), as Netlify Functions execute standard Lambda handlers (`handler(event, context)`). |
| **Static File Delivery** | Django `staticfiles` (`/static/*`) | Built-in routing maps `/static/(.*)` directly to `staticfiles/` via `vercel.json` and static build phase. | Requires manual publishing directory configuration (`publish = "staticfiles"`) or edge redirects. |
| **Function Execution Time** | Heavy ML feature extraction & SHAP explanations | Serverless function timeout configurable up to 60s (Pro/Enterprise) or standard 15s. | Serverless function timeout defaults to 10s (max 26s on standard plans), risking timeouts on multi-step ML inference. |
| **Artifact / Bundle Size** | PyTorch, XGBoost, SHAP, Transformers | Supports up to 250MB uncompressed runtime dependencies in Serverless Functions. | Netlify Functions bundle limit is 50MB zipped / 250MB uncompressed; heavy ML wheels frequently exceed Netlify zip-packager limits. |
| **Asynchronous Workers (Celery)** | Celery Worker + Redis Broker (External) | Decoupled external worker (Railway, Render, AWS ECS) connected via `CELERY_BROKER_URL`. | Identical requirement: Celery cannot run inside Netlify serverless functions. |
| **PostgreSQL Persistence** | PostgreSQL 15 + `psycopg 3` | Managed PostgreSQL (Neon, Supabase, RDS) connected via `DATABASE_URL`. | Identical requirement: Managed external database required. |

---

## 3. Structural Blockers for Direct Netlify Deployment

1. **Lambda Handler Adaptation Requirement:**
   - Netlify serverless functions expect an exported Python function `handler(event, context)`.
   - Running a Django WSGI app on Netlify requires bundling an ASGI/WSGI translation bridge such as `mangum` or `serverless-wsgi`.
   - Modifying entrypoints to depend on Lambda bridge packages adds unnecessary abstraction layers when Vercel natively executes standard WSGI applications.

2. **Function Execution Limits:**
   - Single-incident inference with DistilBERT embeddings and TreeSHAP calculations requires deterministic initialization time and CPU compute.
   - Netlify's 10-second default invocation timeout creates vulnerability to dropped requests during cold-start model weight loads.

3. **Multi-File Django Routing:**
   - Foresight utilizes a rich URL structure across 6 Django apps (`accounts`, `dashboard`, `datasets`, `incidents`, `predictions`, `admin_flow`).
   - Netlify redirects (`[[redirects]] to /.netlify/functions/app`) funnel all requests through a single function gateway, which often strips or alters standard WSGI headers (e.g. `SCRIPT_NAME`, `PATH_INFO`) unless specifically normalized.

---

## 4. Conclusion & Recommendation

In accordance with **RULE 1 (Zero Functional Regression)** and **Section 10 (Netlify Secondary Check)**:

1. **Do not rewrite or restructure** Foresight into Netlify Functions.
2. Maintain **Vercel** as the primary web application deployment target.
3. Deploy the persistent asynchronous processing layer (**Celery worker** and **Redis broker**) on an external worker platform (e.g., Render Background Worker, Railway Service, or AWS ECS/Fargate) connected to managed PostgreSQL.
