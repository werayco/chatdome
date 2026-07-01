import asyncio
import json
from redis.asyncio import Redis
from fastapi import WebSocket
from app.config.settings import settings


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict = {}

    def _get_redis(self) -> Redis:
        return Redis.from_url(settings.REDIS_URL, decode_responses=True)

    async def connect(self, conversation_id, websocket: WebSocket):
        await websocket.accept()
        if conversation_id not in self.active_connections:
            self.active_connections[conversation_id] = []
        self.active_connections[conversation_id].append(websocket)
        asyncio.create_task(self._subscribe(conversation_id, websocket))

    def disconnect(self, conversation_id, websocket: WebSocket):
        if conversation_id in self.active_connections:
            self.active_connections[conversation_id].remove(websocket)

    async def broadcast(self, conversation_id, message: dict):
        async with self._get_redis() as redis:
            await redis.publish(f"conversation:{conversation_id}", json.dumps(message))

    async def _subscribe(self, conversation_id, websocket: WebSocket):
        async with self._get_redis() as redis:
            pubsub = redis.pubsub()
            await pubsub.subscribe(f"conversation:{conversation_id}")
            try:
                async for msg in pubsub.listen():
                    if msg["type"] == "message":
                        data = json.loads(msg["data"])
                        if websocket in self.active_connections.get(conversation_id, []):
                            await websocket.send_json(data)
            finally:
                await pubsub.unsubscribe(f"conversation:{conversation_id}")
                await pubsub.close()


manager = ConnectionManager()