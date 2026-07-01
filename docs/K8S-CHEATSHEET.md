# Top 21 Kubernetes (`kubectl`) Commands

A quick reference for the most commonly used Kubernetes commands.

| Command                                                                         | Purpose                                           |
| ------------------------------------------------------------------------------- | ------------------------------------------------- |
| `kubectl get pods`                                                              | List all pods                                     |
| `kubectl get deployments`                                                       | List deployments                                  |
| `kubectl get services`                                                          | List services                                     |
| `kubectl get nodes`                                                             | List cluster nodes                                |
| `kubectl describe pod <pod-name>`                                               | Show detailed information about a pod             |
| `kubectl logs <pod-name>`                                                       | View pod logs                                     |
| `kubectl logs -f <pod-name>`                                                    | Stream pod logs                                   |
| `kubectl exec -it <pod-name> -- /bin/sh`                                        | Open a shell inside a container                   |
| `kubectl apply -f <file.yaml>`                                                  | Create or update resources from a manifest        |
| `kubectl apply -k <directory>`                                                  | Apply a Kustomize directory                       |
| `kubectl delete -f <file.yaml>`                                                 | Delete resources from a manifest                  |
| `kubectl delete pod <pod-name>`                                                 | Delete a pod                                      |
| `kubectl rollout restart deployment/<deployment-name>`                          | Restart a deployment                              |
| `kubectl rollout status deployment/<deployment-name>`                           | Watch deployment rollout status                   |
| `kubectl scale deployment/<deployment-name> --replicas=<count>`                 | Scale a deployment                                |
| `kubectl port-forward svc/<service-name> <local-port>:<service-port>`           | Access a service locally                          |
| `kubectl get events --sort-by=.metadata.creationTimestamp`                      | Show cluster events                               |
| `kubectl top pods`                                                              | View pod CPU and memory usage                     |
| `kubectl top nodes`                                                             | View node CPU and memory usage                    |
| `kubectl config get-contexts`                                                   | List Kubernetes contexts                          |
| `kubectl wait --for=condition=<condition_type> <resource_type> <resource_name>` | Wait for a resource to reach a specific condition |

---

# Common Examples

## Get Resources

```bash
kubectl get pods
kubectl get deployments
kubectl get services
kubectl get nodes
kubectl get all
kubectl get pods -o wide
kubectl get deployment <deployment-name> -o yaml
kubectl get pods -w
```

---

## Apply & Delete

```bash
kubectl apply -f deployment.yaml

kubectl apply -k deployment/k8s/overlays/minikube

kubectl delete -f deployment.yaml

kubectl delete pod <pod-name>

kubectl delete all --all
```

---

## Describe & Debug

```bash
kubectl describe pod <pod-name>

kubectl describe node <node-name>

kubectl logs <pod-name>

kubectl logs -f <pod-name>

kubectl logs <pod-name> --previous

kubectl exec -it <pod-name> -- /bin/sh
```

---

## Deployments

```bash
kubectl rollout restart deployment/<deployment-name>

kubectl rollout status deployment/<deployment-name>

kubectl rollout history deployment/<deployment-name>

kubectl rollout undo deployment/<deployment-name>

kubectl scale deployment/<deployment-name> --replicas=3
```

---

## Waiting for Resources

Wait until a resource reaches a desired condition.

**Syntax**

```bash
kubectl wait --for=condition=<condition_type> <resource_type> <resource_name> [flags]
```

**Examples**

Wait for a pod to be ready:

```bash
kubectl wait --for=condition=Ready pod/my-pod
```

Wait for a deployment to become available:

```bash
kubectl wait --for=condition=Available deployment/chat-dome-deployment
```

Wait for all pods with a label:

```bash
kubectl wait --for=condition=Ready pod -l app=chatdome
```

Wait with a timeout:

```bash
kubectl wait --for=condition=Ready pod/my-pod --timeout=120s
```

---

## Networking

```bash
kubectl port-forward svc/chat-dome-service 8000:80
```

---

## Monitoring

```bash
kubectl top pods

kubectl top nodes

kubectl get events --sort-by=.metadata.creationTimestamp
```

---

## Context & Namespaces

```bash
kubectl config get-contexts

kubectl config current-context

kubectl config use-context <context-name>

kubectl get ns

kubectl get pods -n kube-system

kubectl config set-context --current --namespace=<namespace>
```

---

## Useful Commands

Edit a resource:

```bash
kubectl edit deployment <deployment-name>
```

Explain a resource schema:

```bash
kubectl explain deployment.spec
```
