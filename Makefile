gen-secret:
	python -c "import secrets; print(secrets.token_urlsafe(64))"
run:
	docker compose -f deployment/docker/docker-compose.yml up --build -d
stop:
	docker compose -f deployment/docker/docker-compose.yml down
recreate:
	docker compose -f deployment/docker/docker-compose.yml up --force-recreate -d
logs:
	docker logs -f chatdome-backend
ps:
	docker ps
get-nodes:
	kubectl get nodes
start-minikube:
	minikube start
add-node:
	minikube node add
pods-nodes-location:
	kubectl get pods -o wide
dev-run:
	kubectl apply -k deployment/k8s/overlays/dev
delete-dev:
	kubectl delete -k deployment/k8s/overlays/dev
glitchtip-migrate:
	docker exec chatdome-glitchtip-web ./manage.py migrate
glitchtip-superuser:
	docker exec -it chatdome-glitchtip-web ./manage.py createsuperuser
glitchtip-logs:
	docker logs -f chatdome-glitchtip-web
glitchtip-worker-logs:
	docker logs -f chatdome-glitchtip-worker
glitchtip-shell:
	docker exec -it chatdome-glitchtip-web ./manage.py shell
backend-shell:
	docker exec -it chatdome-backend /bin/sh
clean:
	docker compose -f deployment/docker/docker-compose.yml down -v