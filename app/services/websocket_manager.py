class ConnectionManager:
    def __init__(self):
        self.active_connections = {}

    async def connect(self, conversation_id, websocket):
        await websocket.accept()

        if conversation_id not in self.active_connections:
            self.active_connections[conversation_id] = []

        self.active_connections[conversation_id].append(websocket)

    def disconnect(self, conversation_id, websocket):
        self.active_connections[conversation_id].remove(websocket)

    async def broadcast(self, conversation_id, message):
        for connection in self.active_connections.get(conversation_id, []):
            await connection.send_json(message)

manager = ConnectionManager()
__all__ = ["manager"]