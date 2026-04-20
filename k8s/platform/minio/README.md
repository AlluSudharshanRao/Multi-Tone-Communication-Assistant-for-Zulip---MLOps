# MinIO (S3-compatible object storage)

PVC uses **`storageClassName: local-path`** (k3s default). Root credentials live in Secret **`minio-root`** (`root-user`, `root-password`); **`deploy_platform.yml`** creates it once with a random password if missing.

Apply after namespaces exist:

```bash
kubectl apply -f ../base/namespaces.yaml
kubectl create secret generic minio-root -n ml-platform --from-literal=root-user=minioadmin --from-literal=root-password='<strong-password>' --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -k .
```

Public HTTPS (Traefik + **`chameleon-nip-tls`**):

- **API:** `https://minio.<floating-ip>.nip.io` (port 443 → Service 9000)
- **Console:** `https://minio-console.<floating-ip>.nip.io` (→ 9001)

Include both hostnames in your TLS cert SANs. For MLflow, you can set `--default-artifact-root=s3://bucket/path` with endpoint `https://minio.<ip>.nip.io` and path-style or virtual-hosted access per client settings.
