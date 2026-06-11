# Running ChatDome on Minikube
Run the full ChatDome stack (API, PostgreSQL, HPA, and Ingress) locally with Minikube.

## Prerequisites

* Minikube
* kubectl
* Docker Desktop (or another Minikube-supported container runtime)

## Start Minikube

```powershell
minikube start --driver=docker
minikube addons enable ingress
minikube addons enable metrics-server
```

## Build the Application Image

Build the image inside Minikube so Kubernetes can access it:

```powershell
minikube image build -t chatdome/app:latest -f deployment/docker/Dockerfile .
```

## Deploy the Stack

```powershell
kubectl apply -k deployment/k8s
kubectl get pods -w
```

Wait until all pods are running.

## Access the API

### Port Forwarding

```powershell
kubectl port-forward svc/chat-dome-service 8000:80
```

Available at:

* http://localhost:8000/health
* http://localhost:8000/docs

### Ingress

Get the Minikube IP:

```powershell
minikube ip
```

Add an entry to your hosts file:

```text
<MINIKUBE_IP> chatdome.local
```

Then access:

```text
http://chatdome.local/health
```

If you're using Windows with the Docker driver, you may need:

```powershell
minikube tunnel
```

and map `chatdome.local` to `127.0.0.1`.

## Useful Commands

```powershell
kubectl get pods,svc,ingress,hpa
kubectl logs -l app=chatdome --tail=50
kubectl logs statefulset/postgres
kubectl get hpa my-app-hpa -w
```

## Updating the Application

Rebuild the image and restart the deployment:

```powershell
minikube image build -t chatdome/app:latest -f deployment/docker/Dockerfile .
kubectl rollout restart deployment/chat-dome-deployment
```

## Cleanup

```powershell
kubectl delete -k deployment/k8s
```

Remove persistent storage:

```powershell
kubectl delete pvc -l app=postgres
```

Or delete the entire cluster:

```powershell
minikube delete
```

## Notes

* The deployment and HPA default to 3 replicas. Reduce them to 1 if your machine is resource-constrained.
* Database tables are created automatically on startup.
* `persistentVolume.yml` is not included in the kustomization because Minikube's default StorageClass provisions storage automatically.
