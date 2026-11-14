# PaperPilot backend - Railway deployment

Security update: registration requires 12–128 characters, uppercase, lowercase,
a digit and a special character. Validation responses omit submitted inputs.
Server quotas persist in `/data/request-limits.sqlite3`: 10 authentication writes
per 10 minutes, 5 uploads/imports/retries per hour, 20 questions per hour per
socket peer. Shared proxy peers share quotas unless trusted forwarding is configured.
Do not trust arbitrary forwarded headers or deploy multiple replicas with this store.
PDF uploads retain the 50 MB limit and PDF signature checks; images are unsupported.
CloudCrane refuses password fields, so the existing mobile email-link flow remains
until a separately hosted authentication page and secure return flow are tested.

FastAPI + ingestion worker + private Chroma, in one service with persistent storage.
Existing Supabase handles authentication, database jobs and private PDFs.

## Railway dashboard deployment

1. Create a project from this GitHub repository. Railway detects the Dockerfile.
2. Stay on free/trial resources only unless you explicitly approve a paid plan.
3. Add a persistent volume mounted at `/data` to the service BEFORE its production use.
4. In Variables, set the five nonempty secrets listed in `.env.example` from your
   existing local environment. Never commit actual values. Set the exact CloudCrane
   origin shown there. The existing Supabase project is reused; no DB reset is needed.
5. Deploy. Wait for `/ready` to return 200, then generate a Railway public domain.
6. Update the CloudCrane private-workspace API hostname AND its blueprint network
   allowlist together. The no-sign-in local sample remains independent of this API.

`start_service.py` starts Chroma on loopback 8001, then one API and one worker.
`PORT` is supplied by Railway. Graphs and vector data are stored under `/data`.
Only the API is exposed. The models are cached in the Docker image during build.
No `.env`, private PDF, vector snapshot or graph data is committed here.

## Existing research migration

This source does not contain personal data. Previously processed papers need their
existing vector/graph data imported privately before switching the production app
to the new backend. A fresh empty index is not proof that existing papers work.
The local working app remains unchanged until deployment and migration are verified.

## Free-trial limits

Railway trial resources have memory and credit limits; a Limited Trial may restrict
outbound access to Supabase/model providers. This deployment is NOT guaranteed to
fit every free account. Do not upgrade automatically or claim production readiness
until `/ready`, authentication, ingestion and a real question are verified.

Deploying the backend does not resolve Supabase email-sender rate limits. Custom
email delivery is a separate optional requirement for external private-workspace use.

## Checks

Source syntax and configuration were checked locally. A container build and live
Railway deployment still need to complete; do not describe this commit as deployed.
