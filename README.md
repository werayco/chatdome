# ChatDome

A real-time chat backend built with FastAPI and PostgreSQL.

Users can register, log in, start direct messages, create group chats, and exchange messages over WebSockets. Authentication is handled with JWTs, data is stored in PostgreSQL, and the application runs in Docker. This repository contains only the backend API.

![alt text](images/image-3.png)
## Features

* User authentication (register, login, refresh tokens, change password)
* Direct messaging between users
* Group chat creation and management
* Real-time messaging with WebSockets
* Role-based group administration
* Docker and Kubernetes deployment support

## Tech Stack

* FastAPI
* PostgreSQL
* SQLAlchemy (async)
* asyncpg
* JWT (python-jose)
* bcrypt
* Pydantic
* Docker & Kubernetes

## Environment Variables

Generate any secret key using:
```bash
make gen-secret
```

Required:

```env
DATABASE_URL=postgresql+asyncpg://db-username:db-password@postgres:5432/dome
JWT_SECRET= # generated secret using the command above
POSTGRES_USER=
POSTGRES_PASSWORD=
POSTGRES_DB=
REDIS_URL=
SECRET_KEY= # generated secret using the command above
PORT=8080
GLITCHTIP_DOMAIN=
DEFAULT_FROM_EMAIL=
EMAIL_URL=consolemail://
ACCOUNT_EMAIL_VERIFICATION=none
GLITCHTIP_DSN=
```

## Quick Start

```bash
docker compose -f deployment/docker/docker-compose.yml up --build -d 
```

(or) You can use the *Make* command. make sure you have *Make* installed on your machine, if you don't have it installed, use 
```bash
sudo apt-get update && sudo apt-get install make
```
After installing, hit:
```bash
Make run
```

Once running:

* API: `http://localhost:8000`
* Health Check: `http://localhost:8000/health`
* Docs: `http://localhost:8000/docs`

# API Endpoints

All HTTP endpoints are prefixed with:

```text
/chat
```

Authentication is required for all endpoints except where stated otherwise.

| Method | Endpoint | Description |
|--------|----------|-------------|
| **POST** | `/conversations/dm` | Creates a direct message (DM) conversation between the authenticated user and another user. If a DM already exists, the existing conversation is returned. |
| **POST** | `/conversations/group` | Creates a new group conversation with the authenticated user as the group administrator and adds the specified members. |
| **GET** | `/conversations/getGroups` | Returns all group conversations that the authenticated user belongs to. |
| **POST** | `/conversations/modify/addUser` | Adds a new user to an existing group conversation. Only group administrators can perform this action. |
| **POST** | `/conversations/modify/changeName` | Changes the name of an existing group conversation. Only group administrators can rename a group. |
| **POST** | `/conversations/modify/makeAdmin` | Make a user an Admin. |
| **POST** | `/conversation/getUsersInConversation` | Returns all members of a specified conversation, including their user information and roles. |

---

# WebSocket Endpoint

```text
ws://localhost:8000/chat/ws/{conversation-id}?token=<access-token>
```

Establishes a real-time WebSocket connection to a conversation.

### Authentication

The JWT access token must be supplied as a query parameter:

```text
?token=<access_token>
```

### Sending Messages

Clients send messages as JSON:

```json
{
  "content": "Hello everyone!"
}
```

### Receiving Messages

Connected clients receive broadcast events whenever a participant sends a message.

Example:

```json
{
  "id": "message-uuid",
  "conversation_id": "conversation-uuid",
  "sender_id": "user-uuid",
  "sender_username": "ray",
  "content": "Hello everyone!",
  "created_at": "2026-07-01T12:00:00.000000"
}
```

## Deployment

Kubernetes manifests are available in [`deployment/k8s/`](./deployment/k8s) for deploying the API, PostgreSQL, ingress, autoscaling, and related resources.