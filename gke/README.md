# Lab 7 on Google Kubernetes Engine

This deploys the same Flask API, Demucs worker, Redis queue, and RustFS
storage used locally. It adds the GKE deployment extra-credit option. The
component `kustomization.yaml` files assemble the existing manifests; the
`gke/` overlay changes image references, selects Google persistent disks,
and replaces nginx ingress with Google's external Application Load Balancer.

## Prerequisites

A billing-enabled Google Cloud project, `gcloud`, `kubectl`, Docker, and the
GKE authentication plugin are required. Google Cloud credits are applied
according to the billing account's credit terms. Resources continue to run
until removed.

All commands below run from the repository root. The project used for this
lab is `csci5253-lab7-shivani2442` in `us-central1-a`. The GKE kubeconfig is
kept in ignored `work/kubeconfig-gke`, separate from the local kind cluster.

```sh
export PROJECT_ID=csci5253-lab7-shivani2442
export REGION=us-central1
export ZONE=us-central1-a
export REGISTRY="$REGION-docker.pkg.dev/$PROJECT_ID/lab7-demucs"
export KUBECONFIG="$PWD/work/kubeconfig-gke"
# This machine's downloaded plugin is under work/. On another machine, install
# it with: gcloud components install gke-gcloud-auth-plugin
export PATH="$PWD/work/gcloud-plugin/bin:$PATH"
```

## One-time infrastructure setup

These resources have already been created for the project above. For a new
project, enable the APIs, create an image repository and node identity, and
create the cluster:

```sh
gcloud services enable compute.googleapis.com container.googleapis.com \
  artifactregistry.googleapis.com iam.googleapis.com --project="$PROJECT_ID"

gcloud artifacts repositories create lab7-demucs \
  --repository-format=docker --location="$REGION" --project="$PROJECT_ID"

gcloud iam service-accounts create lab7-gke-node --project="$PROJECT_ID"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:lab7-gke-node@$PROJECT_ID.iam.gserviceaccount.com" \
  --role=roles/container.defaultNodeServiceAccount --condition=None

gcloud artifacts repositories add-iam-policy-binding lab7-demucs \
  --location="$REGION" --project="$PROJECT_ID" \
  --member="serviceAccount:lab7-gke-node@$PROJECT_ID.iam.gserviceaccount.com" \
  --role=roles/artifactregistry.reader

gcloud container clusters create lab7-demucs \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --num-nodes=1 --machine-type=e2-standard-2 \
  --disk-type=pd-standard --disk-size=30 \
  --release-channel=regular --enable-ip-alias \
  --service-account="lab7-gke-node@$PROJECT_ID.iam.gserviceaccount.com" \
  --scopes=https://www.googleapis.com/auth/cloud-platform
```

A newly created service account may need a short time to propagate before
its IAM bindings can be added. The repository reader role is scoped to the
lab's image repository. The node identity can write its operational logs
and metrics but is not granted project Editor.

## Build, upload, and deploy

The GKE node uses x86-64, so an Apple Silicon Mac must build `linux/amd64`
images. The local ARM images remain available under their original `v1` tags.

```sh
gcloud auth configure-docker "$REGION-docker.pkg.dev"

docker buildx build --platform linux/amd64 --load \
  -f rest/Dockerfile -t "$REGISTRY/demucs-rest:gke-v1" .
docker buildx build --platform linux/amd64 --load \
  -f worker/Dockerfile -t "$REGISTRY/demucs-worker:gke-v1" .
docker push "$REGISTRY/demucs-rest:gke-v1"
docker push "$REGISTRY/demucs-worker:gke-v1"

./gke/deploy.sh
```

`deploy.sh` generates a RustFS password in ignored `work/gke-storage-secret`
and renders the overlay into ignored `work/gke-rendered.yaml`. Keep that
password file for repeat deployments. The password is stored in a Kubernetes
Secret and is not committed. RustFS and Redis have internal ClusterIP services.
Only the REST API is exposed publicly. Each PVC requests 10 GiB using
`standard-rwo`; one caches model weights and one stores the MP3 objects.

## Access and verification

```sh
kubectl get nodes
kubectl get pods,services,pvc,ingress
kubectl describe ingress rest-ingress
```

Google's ingress controller takes several minutes to allocate the IP and
mark the backend healthy. The backend health check uses the API's `/` route
on port 5000. Once ready:

```sh
GKE_IP=$(kubectl get ingress rest-ingress -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
curl --fail "http://$GKE_IP/"
REST="$GKE_IP" .venv/bin/python short-sample-request.py
kubectl logs -f deployment/worker
```

The original sample client returns the song hashes. Its example callback
points to localhost and may fail inside the worker, as permitted by the lab.
Fetch a completed track with a returned hash:

```sh
curl --fail "http://$GKE_IP/apiv1/track/SONG_HASH/vocals.mp3" -o work/gke-vocals.mp3
curl --fail "http://$GKE_IP/apiv1/queue"
```

## Deployment verified on November 3, 2026

- Project: `csci5253-lab7-shivani2442`; cluster: `lab7-demucs`, `us-central1-a`.
- Public REST endpoint: http://34.144.200.1 (while the deployment is running).
- One `e2-standard-2` node; all four lab pods Ready, with zero restarts at validation.
- Both 10 GiB PVCs bound using Google's `standard-rwo` StorageClass.
- Real `mdx_extra_q` separation passed for both supplied short samples.
  The first full smoke test used a GKE API port-forward; the second used
  the public load balancer. Public vocals downloads succeeded for both.
- Four binary MP3 downloads, the `base.mp3` alias, removal, and subsequent
  404 responses passed. The tests remove the bass objects; resubmit a song
  to regenerate them.
- Both stored input files matched the originals byte for byte. All eight
  downloaded cloud tracks were valid stereo MP3 at 44.1 kHz and decoded
  successfully with FFmpeg.

The public endpoint needs no local port-forward. The GKE deployment adds
5 potential extra-credit points to the 5 for RustFS, subject to grading.

## Remove cloud resources after grading

Stopping Docker on your laptop does not stop GKE. To remove this lab's
running cloud resources after the interview, use the dedicated GKE kubeconfig:

```sh
export KUBECONFIG="$PWD/work/kubeconfig-gke"
kubectl delete ingress rest-ingress
# Wait for the ingress-managed load-balancer resources to disappear.
gcloud compute forwarding-rules list --project="$PROJECT_ID"
gcloud container clusters delete lab7-demucs --zone="$ZONE" --project="$PROJECT_ID"
gcloud artifacts repositories delete lab7-demucs --location="$REGION" --project="$PROJECT_ID"
```

Cluster deletion removes the lab's Kubernetes workloads and may delete their
persistent disks. Check for leftover resources in the dedicated project:

```sh
gcloud compute disks list --project="$PROJECT_ID"
gcloud compute addresses list --project="$PROJECT_ID"
gcloud compute forwarding-rules list --project="$PROJECT_ID"
```

References: [GKE external ingress](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/load-balance-ingress),
[GKE health checks](https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/ingress-health-checks).
