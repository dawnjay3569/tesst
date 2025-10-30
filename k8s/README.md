This folder contains Kubernetes manifests and instructions to deploy the FAPI_QExec FastAPI app.

Files:
- `deployment.yaml` - Deployment for the FastAPI app. Edit `image:` to your container registry.
- `service.yaml` - ClusterIP Service exposing the app on port 80 inside the cluster.
- `secret.yaml` - A Secret (stringData) you should edit to include DB credentials or create a secret with `kubectl create secret`.

Quick deploy steps (assumes `kubectl` configured):

1. Build and push image (replace with your registry/name):

```bash
docker build -t <YOUR_REGISTRY>/fapi-qexec:latest .
docker push <YOUR_REGISTRY>/fapi-qexec:latest
```

2. Create secret (edit `k8s/secret.yaml` or create via command):

```bash
# Option A: apply the provided secret (edit stringData values first)
kubectl apply -f k8s/secret.yaml

# Option B: create secret interactively (safer, avoids storing creds in YAML)
kubectl create secret generic fapi-qexec-secrets \
  --from-literal=DB_DRIVER=oracle+oracledb \
  --from-literal=DB_USER=INSIGHTS \
  --from-literal=DB_PASS='yourpass' \
  --from-literal=DB_HOST=SCAN_RPA_PROD01_APP \
  --from-literal=DB_PORT=1977 \
  --from-literal=DB_SERVICE=RPA_PROD01_APP
```

3. Ensure your cluster can reach the configured database. If you use an external Oracle DB,
   no PVC is required for the application.

4. Deploy the app & service:

```bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

5. Check rollout and logs:

```bash
kubectl rollout status deployment/fapi-qexec
kubectl logs -l app=fapi-qexec
kubectl get svc fapi-qexec-svc
```

Notes:
- If you use Oracle in the cluster, install the `oracledb` driver inside the image (already in `requirements.txt`) and ensure the application can reach the Oracle host.
- For quick local testing, use Minikube or Kind and set `imagePullPolicy: IfNotPresent` and `image` to the local image built.
- You may want to create a `ConfigMap` for non-sensitive settings (API keys, logging levels). API keys are currently in `api_keys.json` shipped in the image; consider moving them into a Secret or ConfigMap if needed.
