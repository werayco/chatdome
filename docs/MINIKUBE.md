# Running ChatDome on Locally, using Minikube

Minikube gives the abstraction of running a kubenetes cluster, locally. 

> For the production EC2 setup, see [KUBEADM](KUBEADM.md)

---

## Prerequisites

* Minikube
* kubectl
* Docker Desktop (recommended)


## 1. Download Minikube
Download Minikube [here](https://minikube.sigs.k8s.io/docs/start/?arch=%2Fwindows%2Fx86-64%2Fstable%2F.exe+download) and follow the installation steps.

## 2. Start Minikube

```bash
minikube start --driver=docker --cpus=4 --memory=4096

minikube addons enable ingress
minikube addons enable metrics-server

kubectl wait -n ingress-nginx \
  --for=condition=ready pod \
  -l app.kubernetes.io/component=controller \
  --timeout=120s
```

---
## 3. Add a node into your Minikube Cluster
```console
minikube node add
```
## 4. Create the Secret for the project

```bash
kubectl create secret generic chatdome-secrets \
  --from-literal=DATABASE_URL="postgresql+asyncpg://domeadmin:fXg6jwUyZOt@postgres:5432/dome" \
  --from-literal=JWT_SECRET="OmQhlScwr8PzsdL/3iuXsBjyNDeTSQQdnYmw7xY+KMo=" \
  --from-literal=POSTGRES_USER="domeadmin" \
  --from-literal=POSTGRES_PASSWORD="fXg6jwUyZOt" \
  --from-literal=POSTGRES_DB="dome"
```

---

## 5. Build or Pull the Image

### Use Docker Hub

The deployment already uses:

```
werayco/chatdome:latest
```

### Build Locally

```bash
eval $(minikube docker-env)
docker build -t werayco/chatdome:latest -f deployment/docker/Dockerfile .
```

If building locally, set:

```yaml
imagePullPolicy: Never
```



## 6. Deploy

```bash
kubectl apply -k deployment/k8s/overlays/minikube
```

Watch the rollout:

```bash
kubectl get pods -w
```

Wait until PostgreSQL is running before expecting the API pods to become healthy.

---

## 7. Access the App

### Port Forward

```bash
kubectl port-forward svc/chat-dome-service 8000:80
```

Open:

```
http://localhost:8000/health
http://localhost:8000/docs
```


## Useful Commands

```bash
kubectl get pods,svc,ingress,hpa

kubectl logs -l app=chatdome -f

kubectl logs statefulset/postgres -f

kubectl get hpa my-app-hpa -w

minikube service chat-dome-service --url

minikube dashboard
```

---

## Updating the App

### Local image

```bash
eval $(minikube docker-env)

docker build -t werayco/chatdome:latest \
-f deployment/docker/Dockerfile .

kubectl rollout restart deployment/chat-dome-deployment
```

### Docker Hub image

Update the image tag (if needed) and reapply:

```bash
kubectl apply -k deployment/k8s/overlays/minikube
```

---

## Docker Compose

For local backend development without Kubernetes:

```bash
cd deployment/docker
docker compose up
```

API:

```
http://localhost:8000
```

---

