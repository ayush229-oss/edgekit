# Deploy pipeline check

Trivial marker file used to verify that pushing to `main` triggers the
`edgekit` Vercel project to auto-build and auto-assign the production domains
(edgekit.uk / www.edgekit.uk) without a manual `vercel alias`.

- 2026-06-12: auto-deploy verification push.
- 2026-06-13: backend auto-deploy verification — Railway `edgekit-v2` service now git-connected to ayush229-oss/edgekit @ main.
