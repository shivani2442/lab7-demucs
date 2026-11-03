#!/bin/sh
# Build/load demucs-rest:v1 and demucs-worker:v1 into the local cluster first.
set -eu
cd "$(dirname "$0")"
kubectl apply -f redis/redis-deployment.yaml -f redis/redis-service.yaml
kubectl apply -f rustfs/rustfs.yaml
kubectl rollout status deployment/redis --timeout=180s
kubectl rollout status deployment/rustfs --timeout=180s
kubectl apply -f rest/rest-deployment.yaml -f rest/rest-service.yaml -f rest/rest-ingress.yaml
kubectl apply -f worker/worker-deployment.yaml
kubectl rollout status deployment/rest-server --timeout=180s
kubectl rollout status deployment/worker --timeout=180s
