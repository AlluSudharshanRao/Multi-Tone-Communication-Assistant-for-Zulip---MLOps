# Security (public repository)

This repo is safe to share **only if** real secrets and environment-specific identifiers stay local.

## Do not commit

- OpenStack **application credential** secrets, passwords, or filled-in `terraform.tfvars`
- **SSH private keys** (`.pem`, `id_*`), real `inventory.ini`, or kubeconfig files
- **`values-secret.yaml`** (Zulip DB passwords, `SECRETS_secret_key`, etc.)
- Kubernetes **TLS keys**, raw `Secret` manifests with real data, or API tokens
- The **`grafana-admin`** Secret (created on-cluster by Ansible or `kubectl`) — never commit its YAML export

`.gitignore` is meant to block the usual paths; always run `git status` and `git diff --cached` before pushing.

## Placeholders and environment-specific values in tracked files

Many examples use **RFC 5737** documentation addresses (e.g. `203.0.113.10`) or fictional UUIDs. Some **Kubernetes Ingress** and Helm **host** fields may instead pin **one team floating IP** consistently across manifests. Before deploying—or before publishing a fork—replace those values with **your** floating IP, reservation IDs, and network IDs so hosts, TLS SANs, and `SETTING_EXTERNAL_HOST` stay aligned.

## If something was exposed

1. **Rotate** the affected OpenStack credentials, Zulip/chart passwords, and TLS certs.
2. If a secret ever reached **git history**, use [git filter-repo](https://github.com/newren/git-filter-repo) (or GitHub support) to purge it, then force-push; rotating credentials is still required.

## Reporting

If you find committed credentials, open a **private** GitHub security advisory for this repository or contact the maintainers without pasting the secret in public issues.
