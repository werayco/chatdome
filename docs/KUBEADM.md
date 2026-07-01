# Deploying ChatDome on a Self-Managed K8s Cluster on AWS EC2, using Kubeadm

This documents the full process of building a production-grade Kubernetes cluster from scratch on AWS EC2 and deploying the ChatDome application on it.

> For local development, use [MINIKUBE.md](MINIKUBE.md) instead. This file is the production/EC2 path.

---

## Architecture Overview

```
Internet
    ↓
AWS Network Load Balancer
    ↓
Traefik (Ingress Controller)
    ↓
Kubernetes Ingress Rules
    ↓
ChatDome FastAPI App  ←→  PostgreSQL
```

**Stack:**
- Kubernetes v1.31.14 (kubeadm)
- Ubuntu 24.04 on all nodes
- containerd 2.2.1 runtime
- Flannel CNI (For Ip allocation)
- AWS Cloud Controller Manager (CCM)
- Traefik v3 ingress controller
- cert-manager + Let's Encrypt (HTTP-01)
- ArgoCD for GitOps

**Nodes:**

| Role | Hostname | Private IP | AZ |
|------|----------|------------|-----|
| Control Plane | control-plane | 172.31.45.67 | us-east-1d |
| Worker 1 | worker-node-1 | 172.31.28.64 | us-east-1c |
| Worker 2 | worker-node-2 | 172.31.27.197 | us-east-1c |

---

## EC2 Prerequisites

Provision **3 instances** (Ubuntu 24.04, t3.medium or larger). Note the control-plane's **private** IP and each worker's **public** IP.

### Security groups

Create one security group shared by all nodes:

| Port range | Source | Purpose |
|---|---|---|
| 22 | your ip | SSH |
| 6443 | SG + your ip | Kubernetes API server |
| 2379-2380 | SG | etcd (control-plane only) |
| 10250 | SG | kubelet |
| 10257, 10259 | SG | controller-manager, scheduler |
| 30000-32767 | SG | NodePort range |
| 80, 443 | 0.0.0.0/0 | Traefik + ACME HTTP-01 challenge |
| all | SG itself | pod/CNI traffic between nodes |

> The "all traffic from the SG to itself" rule is the one most kubeadm guides omit. Without it, pod-to-pod networking across nodes silently fails.

---

## Phase 1 - Prepare Every Node (run on ALL 3)

## Running Commands Across Multiple Nodes with tmux

To run the same command across multiple nodes simultaneously, use **tmux**. This allows you to type a command once and have it executed in every terminal pane.

> **Prerequisite:** SSH into the **control plane** from VS Code before following these steps.

### i. Start a tmux Session

Create a new tmux session by creating a new tmux terminal:

### ii. Split the Terminal into Multiple Panes

Since this cluster has **2 worker nodes**, you'll need **3 panes total** (1 control plane + 2 workers).

To create additional panes:

- Press **Ctrl + b**, then press **"** (double quote) to split the current pane horizontally.
- Repeat the same shortcut once more to create a third pane.

---

### iii. Enable Synchronized Input

To send the same keystrokes to every pane:

1. Press **Ctrl + b**
2. Press **:**
3. Type the following command and press **Enter**:

```text
setw synchronize-panes on
```

---

### iv. Connect Each Pane to a Different Node

SSH into a different node in each pane.

For example:

- **Pane 1:** Control Plane
- **Pane 2:** Worker Node 1
- **Pane 3:** Worker Node 2

---

### v. Run Commands Across All Nodes

With synchronized input enabled, any command you type in one pane will automatically be executed in every pane.

Now, paste and run the command below, and it will execute simultaneously on all connected nodes.



```bash
# disable swap - kubelet requires it off
sudo swapoff -a
sudo sed -i '/ swap / s/^/#/' /etc/fstab

# kernel modules and sysctl for container networking
cat <<EOF | sudo tee /etc/modules-load.d/k8s.conf
overlay
br_netfilter
EOF
sudo modprobe overlay && sudo modprobe br_netfilter

cat <<EOF | sudo tee /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF
sudo sysctl --system

# installing a container runtime (containerd)
sudo apt-get update && sudo apt-get install -y containerd
sudo mkdir -p /etc/containerd
containerd config default | sudo tee /etc/containerd/config.toml >/dev/null
sudo sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml
sudo systemctl restart containerd

# kubeadm, kubelet, kubectl
sudo apt-get install -y apt-transport-https ca-certificates curl gpg
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.31/deb/Release.key \
  | sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.31/deb/ /' \
  | sudo tee /etc/apt/sources.list.d/kubernetes.list
sudo apt-get update && sudo apt-get install -y kubelet kubeadm kubectl
sudo apt-mark hold kubelet kubeadm kubectl
```

---

## Phase 2 - Bootstrap the Cluster

### Control-plane node only

```bash
sudo kubeadm init \
  --pod-network-cidr=10.244.0.0/16 \
  --cri-socket=unix:///run/containerd/containerd.sock

mkdir -p ~/.kube
sudo cp /etc/kubernetes/admin.conf ~/.kube/config
sudo chown $(id -u):$(id -g) ~/.kube/config

# Install Flannel CNI
kubectl apply -f https://raw.githubusercontent.com/flannel-io/flannel/master/Documentation/kube-flannel.yml
```

`kubeadm init` prints a `kubeadm join` command. Copy it.

### Each worker node

```bash
sudo kubeadm join <CONTROL_PLANE_PRIVATE_IP>:6443 --token <...> \
  --discovery-token-ca-cert-hash sha256:<...>
```

### Verify

```bash
kubectl get nodes   # all 3 should reach Ready once Flannel is up
```

---

## Phase 3 - AWS IAM Setup

An IAM role called `KubernetesNodeRole` was created and attached directly to every EC2 instance. This is what allows the AWS Cloud Controller Manager to make API calls to AWS on behalf of the cluster - creating load balancers, registering targets, managing security group rules.

The role needs permissions covering EC2 describe operations and the full ELB/ELBv2 API surface.

Verify the role is reachable from each node using IMDSv2:

```bash
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")

curl -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/iam/security-credentials/
# should return: KubernetesNodeRole
```

---

## Phase 4 - AWS Cloud Controller Manager (CCM)

Without CCM, Kubernetes has no way to talk to AWS. When a `Service` of type `LoadBalancer` is created, something needs to translate that into actual AWS API calls. CCM is that bridge, it creates the NLB, registers node targets, and fills in the `EXTERNAL-IP` field on the service.

### Configure external cloud provider

Add `--cloud-provider=external` to `/etc/kubernetes/manifests/kube-apiserver.yaml`. This tells Kubernetes to defer all cloud operations to an external controller.

### Tag EC2 instances

CCM discovers which instances belong to the cluster via a tag. Apply this to every EC2 instance:

```
Key:   KubernetesCluster
Value: kubernetes
```

The value must match the `clusterName` from kubeadm-config (default is `kubernetes`).

### Install CCM via Helm

```bash
helm repo add aws-cloud-controller-manager \
  https://kubernetes.github.io/cloud-provider-aws

helm install aws-cloud-controller-manager \
  aws-cloud-controller-manager/aws-cloud-controller-manager \
  -n kube-system \
  --set args[0]="--v=2" \
  --set args[1]="--cloud-provider=aws" \
  --set args[2]="--cluster-name=kubernetes" \
  --set args[3]="--configure-cloud-routes=false"
```

`--configure-cloud-routes=false` is required when using a CNI overlay like Flannel. The route controller is only needed when using AWS VPC routing without an overlay - with Flannel it crashes immediately because it tries to read a CIDR that isn't passed to it.

### Patch node ProviderIDs

On a kubeadm cluster, `spec.providerID` is never set automatically. CCM needs it to match a Kubernetes node to its EC2 instance. Run this on each node to get the value:

```bash
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")

echo "aws:///$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/placement/availability-zone)/$(curl -s \
  -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/instance-id)"
```

Then patch each node from the control plane:

```bash
kubectl patch node control-plane \
  -p '{"spec":{"providerID":"aws:///us-east-1d/i-0626b151159b77f7b"}}'

kubectl patch node worker-node-1 \
  -p '{"spec":{"providerID":"aws:///us-east-1c/i-00557179103e23df4"}}'

kubectl patch node worker-node-2 \
  -p '{"spec":{"providerID":"aws:///us-east-1c/i-0ba50cbaff0bc8fbc"}}'
```

The format is always `aws:///<availability-zone>/<instance-id>`.

---

## Phase 5 - Subnet and VPC Tags

CCM discovers which subnets to place the NLB in via tags. Two tags are required on every subnet you want eligible:

```
kubernetes.io/role/elb=1                   - marks subnet as eligible for internet-facing LBs
kubernetes.io/cluster/kubernetes=shared    - scopes the subnet to this cluster
```

Tag all subnets in the VPC:

```bash
aws ec2 create-tags \
  --resources \
    subnet-042492bada9182300 \
    subnet-0d41df4460aa9c2fb \
    subnet-019f9ecc192abd0a9 \
    subnet-09b181634cedecaf5 \
    subnet-00289dc05ea447773 \
    subnet-07afa34e59d6e21f9 \
  --tags \
    Key=kubernetes.io/role/elb,Value=1 \
    Key=kubernetes.io/cluster/kubernetes,Value=shared
```

Tag the VPC itself:

```bash
aws ec2 create-tags \
  --resources vpc-01082be922b56693e \
  --tags Key=kubernetes.io/cluster/kubernetes,Value=shared
```

Make sure subnets in every AZ your nodes live in are tagged. CCM needs at least one eligible subnet per AZ to register targets.

---

## Phase 6 - Traefik with NLB

Traefik was installed via Helm with a `LoadBalancer` service type. Without the NLB annotation, CCM creates a Classic ELB by default.

```bash
cat > traefik-values.yaml << 'EOF'
service:
  type: LoadBalancer
  annotations:
    service.beta.kubernetes.io/aws-load-balancer-type: "nlb"
    service.beta.kubernetes.io/aws-load-balancer-scheme: "internet-facing"
    service.beta.kubernetes.io/aws-load-balancer-cross-zone-load-balancing-enabled: "true"

ports:
  web:
    port: 80
    exposedPort: 80
  websecure:
    port: 443
    exposedPort: 443

ingressClass:
  enabled: true
  isDefaultClass: true
EOF

helm install traefik traefik/traefik \
  -n traefik \
  --create-namespace \
  -f traefik-values.yaml
```

CCM picks up the service and provisions the NLB within seconds. The `EXTERNAL-IP` field on the service populates with the NLB DNS name. Verify Traefik is reachable:

```bash
curl http://<nlb-dns-name>
```

---

## Phase 7 - Supporting Cluster Components

### metrics-server

Required for the HPA to read CPU metrics. The `--kubelet-insecure-tls` flag is needed because kubeadm kubelets use self-signed certificates.

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

kubectl -n kube-system patch deployment metrics-server --type=json \
  -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
```

Verify after a minute:

```bash
kubectl top nodes
```

### cert-manager

```bash
helm repo add jetstack https://charts.jetstack.io
helm repo update

helm install cert-manager jetstack/cert-manager \
  -n cert-manager \
  --create-namespace \
  --set crds.enabled=true
```

Wait for all three pods to reach `1/1 Running`:

```bash
kubectl get pods -n cert-manager -w
```

Then apply the ClusterIssuer. 
```bash
kubectl apply -f deployment/k8s/cluster-addons/cluster-issuer.yml
kubectl get clusterissuer letsencrypt-prod   # wait for READY: True
```

### ArgoCD

Installed at v3.3.11. The `--server-side --force-conflicts` flags are required from v3.3+ because some CRDs exceed the client-side apply size limit.

```bash
kubectl create namespace argocd

kubectl apply -n argocd \
  --server-side --force-conflicts \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/v3.3.11/manifests/install.yaml
```

Patch the server to serve plain HTTP - Traefik handles TLS termination, so ArgoCD doesn't need to do it internally:

```bash
kubectl patch deployment argocd-server \
  -n argocd \
  --type=json \
  -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--insecure"}]'
```

Get the initial admin password:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d && echo
```

The ArgoCD ingress is applied manually as a one-time bootstrap step. It lives in the `argocd` namespace and must not be managed by ArgoCD itself - that would create a circular dependency where ArgoCD needs to be reachable to sync the manifest that exposes it.

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: argocd-ingress
  namespace: argocd
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    traefik.ingress.kubernetes.io/router.entrypoints: web,websecure
    traefik.ingress.kubernetes.io/router.tls: "true"
spec:
  ingressClassName: traefik
  tls:
    - hosts:
        - argocd.devrayco.name.ng
      secretName: argocd-tls-secret
  rules:
    - host: argocd.devrayco.name.ng
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: argocd-server
                port:
                  number: 80
```

```bash
kubectl apply -f deployment/k8s/cluster-addons/argocd-ingress.yml
```

---

## Phase 8 - DNS

All hostnames point to the NLB via CNAME records:

```
chatdome.devrayco.name.ng  CNAME  <nlb-dns-name>.elb.us-east-1.amazonaws.com
argocd.devrayco.name.ng    CNAME  <nlb-dns-name>.elb.us-east-1.amazonaws.com
```

If using Cloudflare, set both records to DNS-only (grey cloud). The Cloudflare proxy intercepts TLS and breaks the cert-manager HTTP-01 challenge.

Verify propagation:

```bash
nslookup chatdome.devrayco.name.ng
```

---

## Phase 9 - Application Deployment

### Pre-deployment steps

Create the postgres data directory on worker-node-1 (where the StatefulSet is pinned via nodeAffinity):

```bash
# SSH into worker-node-1
sudo mkdir -p /data/postgres
sudo chown -R 1000:1000 /data/postgres
```

Create the application secret - never commit credentials to git:

```bash
kubectl create secret generic chatdome-secrets \
  --from-literal=DATABASE_URL="postgresql+asyncpg://domeadmin:db-password@postgres:5432/dome" \
  --from-literal=POSTGRES_USER="domeadmin" \
  --from-literal=POSTGRES_PASSWORD="db-password" \
  --from-literal=POSTGRES_DB="dome" \
  --from-literal=SECRET_KEY="" \
  --from-literal=JWT_SECRET="" \
  --from-literal=PORT="8000" \
  --from-literal=REDIS_URL="redis://chatdome-redis:6379" \
  --from-literal=GLITCHTIP_DOMAIN="https://errors.devrayco.name.ng" \
  --from-literal=DEFAULT_FROM_EMAIL="errors@devrayco.name.ng" \
  --from-literal=EMAIL_URL="consolemail://" \
  --from-literal=GLITCHTIP_DSN="https://dsn-gotten-from-glitchtip-ui"
```

### Deploy via ArgoCD

Apply the ArgoCD Application once:

```bash
kubectl apply -f deployment/argocd/application.yml
```

ArgoCD clones the repo, finds `deployment/k8s/kustomization.yaml`, and runs `kubectl apply -k` on it automatically. Every push to main triggers a sync. The kustomization manages:

- StorageClass (local-path for postgres)
- PersistentVolume (pinned to worker-node-1)
- PostgreSQL StatefulSet + headless Service
- ChatDome Deployment + ClusterIP Service
- HPA (3-10 replicas, 50% CPU target)
- Ingress

Watch the sync:

```bash
kubectl get application -n argocd chatdome -w
kubectl get pods -w
```

Watch the certificate get issued:

```bash
kubectl get certificate -w
```

---

## How TLS Issuance Works

When the Ingress is applied, cert-manager's ingress-shim detects the `cert-manager.io/cluster-issuer` annotation and creates a `Certificate` object named after `secretName`. Three Kubernetes objects are involved:

| Object | Name | Purpose |
|---|---|---|
| Certificate | `chatdome-tls-secret` | Declares what cert you want and where to store it |
| CertificateRequest | `chatdome-tls-secret-1` | The actual CSR sent to Let's Encrypt |
| Secret | `chatdome-tls-secret` | Stores the final `tls.crt` and `tls.key` |

For HTTP-01 challenges:

1. cert-manager creates a temporary Ingress rule serving a token at `/.well-known/acme-challenge/<token>`
2. Let's Encrypt fetches that URL to verify you control the domain
3. On success, Let's Encrypt signs and returns the certificate
4. cert-manager stores it in the Secret - Traefik picks it up automatically

The Challenge object exists only while verification is in flight and is cleaned up automatically.
