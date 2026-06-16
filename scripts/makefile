jwt:
	python -c "import secrets; print(secrets.token_urlsafe(64))"
	
run:
	uvicorn app.main:app --reload --port 8989

get-nodes:
	kubectl get nodes

start-minikube:
	minikube start

pods-nodes-location:
	kubectl get pods -o wide

kustomize-deploy:
	kubectl apply -k deployment/k8s
