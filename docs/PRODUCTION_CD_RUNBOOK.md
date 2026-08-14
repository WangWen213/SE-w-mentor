# SE-Mentor Production CD Runbook

Production URL: `https://47.76.106.57`

Production repository on ECS: `/opt/se-mentor`

Production runtime profile: `ONLINE_SAFE`

TLS certificate material is host-managed outside Git. GitHub Actions must never receive or write
TLS private keys, OpenAI-compatible user credentials, browser session credentials, or API keys.

## Deployment Model

```text
push main
-> GitHub Actions CI
-> CI success only
-> Production Deploy workflow
-> SSH to ECS
-> /opt/se-mentor fast-forwards to origin/main
-> docker compose production build
-> backend entrypoint runs Alembic upgrade head
-> backend/frontend/gateway are recreated
-> health and ONLINE_SAFE runtime verification
```

The production deploy workflow is also available through `workflow_dispatch`. The automatic path is
gated by `workflow_run` and only runs after the `CI` workflow concludes successfully on `main`.

If deployment secrets are missing, the workflow skips before SSH and performs no remote mutation.
Once secrets are configured, missing or invalid ECS host configuration fails the deployment.

## Required GitHub Secrets

- `SE_MENTOR_DEPLOY_HOST`: `47.76.106.57`
- `SE_MENTOR_DEPLOY_USER`: the dedicated deploy user on ECS
- `SE_MENTOR_DEPLOY_SSH_KEY`: the private key for that deploy user
- `SE_MENTOR_DEPLOY_KNOWN_HOSTS`: pinned known_hosts entry for `47.76.106.57`

Do not paste the private key into Codex or commit it to Git. Put it directly into the GitHub
repository secret UI.

## Required ECS Host File

Create `/etc/se-mentor/production.env` on ECS. It must not be committed.

```sh
sudo install -d -m 0755 /etc/se-mentor
sudo tee /etc/se-mentor/production.env >/dev/null <<'EOF'
SE_MENTOR_RUNTIME_PROFILE=ONLINE_SAFE
SE_MENTOR_TRUST_PROXY=true
SE_MENTOR_TLS_CERT_DIR=/etc/se-mentor/tls
SE_MENTOR_ACME_WEBROOT=/var/lib/se-mentor/acme-webroot
EOF
sudo chmod 0644 /etc/se-mentor/production.env
```

The deployment script only accepts those four keys. Production must not silently fall back to
`CLOUD_DEMO`.

## Required TLS Paths

The host must already contain:

```text
/etc/se-mentor/tls/fullchain.pem
/etc/se-mentor/tls/privkey.pem
/var/lib/se-mentor/acme-webroot/
```

Certificate issuance and renewal are separate host-managed tasks. The CD workflow validates the
files exist but does not request, overwrite, or regenerate certificates.

## Dedicated SSH Key Setup

Run these steps on a trusted user machine and the ECS host. Do not share the private key with Codex.

1. Create a deploy key on your machine:

   ```sh
   ssh-keygen -t ed25519 -C "se-mentor-production-deploy" -f ./se-mentor-production-deploy
   ```

2. Add the public key to the ECS deploy user's `authorized_keys`:

   ```sh
   ssh-copy-id -i ./se-mentor-production-deploy.pub <deploy-user>@47.76.106.57
   ```

   Or append the `.pub` file contents to:

   ```text
   /home/<deploy-user>/.ssh/authorized_keys
   ```

3. Ensure the deploy user can run the required production commands in `/opt/se-mentor`:

   ```sh
   cd /opt/se-mentor
   git status
   docker compose version
   ```

4. Capture the pinned host key from your machine:

   ```sh
   ssh-keyscan -H 47.76.106.57
   ```

   Verify the fingerprint out-of-band before storing the output as `SE_MENTOR_DEPLOY_KNOWN_HOSTS`.

## GitHub Secret Setup

In GitHub repository settings, add:

```text
SE_MENTOR_DEPLOY_HOST=47.76.106.57
SE_MENTOR_DEPLOY_USER=<deploy-user>
SE_MENTOR_DEPLOY_SSH_KEY=<contents of se-mentor-production-deploy private key>
SE_MENTOR_DEPLOY_KNOWN_HOSTS=<verified ssh-keyscan known_hosts line>
```

The private key goes directly from your machine to GitHub Actions Secrets. Do not paste it into a
chat, issue, commit, or log.

## Emergency Manual Deployment Equivalent

Run manually on ECS only when you intentionally deploy:

```sh
cd /opt/se-mentor
scripts/deploy_production.sh
```

The script refuses a dirty tracked working tree, refuses non-`main`, fetches `origin/main`, performs
`git merge --ff-only origin/main`, validates `/etc/se-mentor/production.env`, validates TLS files,
builds backend/frontend images, recreates backend/frontend/gateway with production Compose, and
requires health/runtime checks before reporting success.

## Manual Rollback Procedure

No destructive automatic rollback is implemented. If deployment fails, inspect the GitHub Actions
log and ECS Docker logs. To roll back, intentionally redeploy a known-good Git commit or image in a
separate manual operation. Do not run `git reset --hard`, `git clean`, or `docker compose down -v`
as part of this CD workflow.
