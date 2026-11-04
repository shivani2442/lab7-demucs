#!/bin/sh
# Apply the GKE overlay after creating the cluster and uploading both images.
set -eu
cd "$(dirname "$0")/.."
: "${PROJECT_ID:?Set PROJECT_ID to your Google Cloud project ID}"
REGION=${REGION:-us-central1}
ZONE=${ZONE:-us-central1-a}
CLUSTER=${CLUSTER:-lab7-demucs}
REGISTRY="$REGION-docker.pkg.dev/$PROJECT_ID/lab7-demucs"
export KUBECONFIG="$PWD/work/kubeconfig-gke"
export PATH="$PWD/work/gcloud-plugin/bin:$PATH"
mkdir -p work
cluster_status=$(gcloud container clusters describe "$CLUSTER" --zone "$ZONE" --project "$PROJECT_ID" --format='value(status)')
if [ "$cluster_status" != RUNNING ]; then
    echo "Cluster is $cluster_status; wait until it is RUNNING before deploying." >&2
    exit 1
fi
gcloud container clusters get-credentials "$CLUSTER" --zone "$ZONE" --project "$PROJECT_ID"
# Keep a consistent storage password across redeployments, outside version control.
if [ ! -s work/gke-storage-secret ]; then
    (umask 077; python3 -c 'import secrets; print(secrets.token_hex(32))' > work/gke-storage-secret)
fi
kubectl kustomize gke > work/gke-template.yaml
python3 - "$REGISTRY" <<'PY'
from pathlib import Path
import os
import sys
source = Path('work/gke-template.yaml').read_text()
source = source.replace('REGISTRY/', sys.argv[1] + '/')
source = source.replace('replace-this-demo-secret', Path('work/gke-storage-secret').read_text().strip())
path = Path('work/gke-rendered.yaml')
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as output:
    output.write(source)
PY
kubectl apply -f work/gke-rendered.yaml
kubectl rollout status deployment/redis --timeout=600s
kubectl rollout status deployment/rustfs --timeout=600s
kubectl rollout status deployment/rest-server --timeout=600s
kubectl rollout status deployment/worker --timeout=600s
kubectl get pods,services,ingress,pvc
