# Deploying ChatDome on a self-managed kubeadm cluster (EC2)

This guide stands up a 3-node Kubernetes cluster on EC2 (**1 control-plane + 2
workers**) with `kubeadm`, then installs the add-ons that Minikube used to give
you for free (ingress, metrics, storage) and serves the app over HTTPS on a real
domain.

> For local development use [../MINIKUBE.md](../MINIKUBE.md) instead. This file
> is the production/EC2 path.

## Why these add-ons are needed

Minikube bundled four things a bare kubeadm cluster does **not** have. Each phase
below installs one:

| Minikube gave you            | kubeadm equivalent installed here          |
| ---------------------------- | ------------------------------------------ |
| `addons enable ingress`      | ingress-nginx via Helm (hostNetwork)       |
| `addons enable metrics-server` | metrics-server (needed by the HPA)       |
| default StorageClass         | rancher local-path-provisioner             |
| (no TLS)                     | cert-manager + Let's Encrypt ClusterIssuer |

---

## Phase 0 — EC2 prerequisites

Provision **3 instances** (Ubuntu 22.04, t3.medium or larger). Note the
control-plane's **private** IP and each worker's **public** IP.

### Security groups

Create one SG shared by all nodes and add:

| Port range    | Source           | Purpose                                  |
| ------------- | ---------------- | ---------------------------------------- |
| 22            | your IP          | SSH                                       |
| 6443          | SG + your IP     | Kubernetes API server                     |
| 2379-2380     | SG               | etcd (control-plane only)                 |
| 10250         | SG               | kubelet                                   |
| 10257, 10259  | SG               | controller-manager, scheduler             |
| 30000-32767   | SG               | NodePort range                            |
| **80, 443**   | **0.0.0.0/0**    | ingress-nginx (hostPort) + ACME HTTP-01   |
| all           | **SG itself**    | pod/CNI traffic between nodes             |

> The "all traffic from the SG to itself" rule is the one most kubeadm guides
> omit — without it pod-to-pod networking across nodes silently fails.

---

## Phase 1 — Prepare every node (run on ALL 3)

```bash
# Disable swap (kubelet requires it off)
sudo swapoff -a
sudo sed -i '/ swap / s/^/#/' /etc/fstab

# Kernel modules + sysctl for the container network
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

# containerd runtime
sudo apt-get update && sudo apt-get install -y containerd
sudo mkdir -p /etc/containerd
containerd config default | sudo tee /etc/containerd/config.toml >/dev/null
# Use the systemd cgroup driver (must match kubelet)
sudo sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml
sudo systemctl restart containerd

# kubeadm, kubelet, kubectl
sudo apt-get install -y apt-transport-https ca-certificates curl gpg
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.30/deb/Release.key \
  | sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.30/deb/ /' \
  | sudo tee /etc/apt/sources.list.d/kubernetes.list
sudo apt-get update && sudo apt-get install -y kubelet kubeadm kubectl
sudo apt-mark hold kubelet kubeadm kubectl
```

---

## Phase 2 — Bootstrap the cluster

### Control-plane node only

```bash
sudo kubeadm init --pod-network-cidr=192.168.0.0/16

# Configure kubectl for your user
mkdir -p $HOME/.kube
sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config

# CNI (Calico) — its default pool matches the CIDR above
kubectl apply -f https://raw.githubusercontent.com/projectcalico/calico/v3.27.0/manifests/calico.yaml
```

`kubeadm init` prints a `kubeadm join ... --token ...` command. Copy it.

### Each worker node

```bash
sudo kubeadm join <CONTROL_PLANE_PRIVATE_IP>:6443 --token <...> \
  --discovery-token-ca-cert-hash sha256:<...>
```

### Verify (on control-plane)

```bash
kubectl get nodes      # all 3 should reach Ready once Calico is up
```

---

## Phase 3 — Cluster add-ons

Run all of these from the control-plane.

### 3a. Storage — default StorageClass

Fixes the Postgres PVC sitting `Pending` (kubeadm has no provisioner).

```bash
kubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/v0.0.28/deploy/local-path-storage.yaml
kubectl patch storageclass local-path \
  -p '{"metadata":{"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
```

> local-path stores PVC data on the node's local disk, so the Postgres pod is
> pinned to whichever node first scheduled it. Fine for a 1-replica DB. For
> production durability, consider AWS RDS or the EBS CSI driver instead.

### 3b. metrics-server (required by the HPA)

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
# kubeadm kubelets use self-signed certs — let metrics-server accept them:
kubectl -n kube-system patch deployment metrics-server --type=json \
  -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
```

### 3c. ingress-nginx (bound to host ports, not a cloud LB)

On kubeadm a `LoadBalancer` Service stays `<pending>` forever. Bind nginx
directly to ports 80/443 on the workers instead:

```bash
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update
helm install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx --create-namespace \
  --set controller.kind=DaemonSet \
  --set controller.hostNetwork=true \
  --set controller.service.type=ClusterIP
```

### 3d. cert-manager + ClusterIssuer

```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml
kubectl -n cert-manager rollout status deploy/cert-manager-webhook   # wait until ready

# Edit cluster-issuer.yml first: set your email, then:
kubectl apply -f cluster-issuer.yml
```

---

## Phase 4 — App changes & DNS

1. **Push the image to Docker Hub** and update
   [../chat-deployment.yml](../chat-deployment.yml) `image:` to
   `docker.io/<dockerhubuser>/chatdome:<tag>` (use a real tag, not `latest`).

2. **Point DNS** — create an A record for your domain pointing at a worker's
   **public IP** (or an AWS NLB fronting both workers' :80/:443). Wait for it to
   resolve before requesting a cert.

3. **Update the ingress** ([../ingress.yml](../ingress.yml)) — set the real
   `host:`, add the cert-manager annotation and a `tls:` block:

   ```yaml
   metadata:
     name: chatdome-ingress
     annotations:
       cert-manager.io/cluster-issuer: letsencrypt-prod
   spec:
     ingressClassName: nginx
     tls:
       - hosts:
           - chat.yourdomain.com
         secretName: chatdome-tls
     rules:
       - host: chat.yourdomain.com
         http:
           paths:
             - path: /
               pathType: Prefix
               backend:
                 service:
                   name: chat-dome-service
                   port:
                     number: 80
   ```

4. **Deploy the app:**

   ```bash
   kubectl apply -k ..        # applies the kustomization in deployment/k8s
   kubectl get pods,svc,ingress,hpa -w
   ```

5. **Watch the certificate** get issued (HTTP-01 over port 80):

   ```bash
   kubectl get certificate
   kubectl describe certificate chatdome-tls   # should reach Ready=True in ~1 min
   ```

   Then browse to `https://chat.yourdomain.com/health`.

> Tip: test with `letsencrypt-staging` first (swap the annotation) to avoid
> Let's Encrypt's production rate limits, then switch to `letsencrypt-prod`.

---

## Troubleshooting

| Symptom                              | Likely cause / fix                                            |
| ------------------------------------ | ------------------------------------------------------------- |
| Postgres pod `Pending`               | No default StorageClass — redo 3a.                            |
| HPA shows CPU `<unknown>`            | metrics-server missing/not ready — redo 3b.                  |
| App pods `ErrImagePull`              | Image not on Docker Hub, or private repo needs an imagePullSecret. |
| Certificate stuck `False`            | DNS not resolving to cluster, or port 80 blocked in the SG.  |
| Workers `NotReady`                   | CNI not installed, or SG missing the "SG-to-itself" rule.    |
