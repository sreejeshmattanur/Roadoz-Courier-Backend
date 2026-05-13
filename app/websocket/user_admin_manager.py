from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active_connections = {}
    async def connect(self,user_type: str,user_id:str,websocket: WebSocket):
        await websocket.accept()
        key = f"{user_type}_{user_id}"
        self.active_connections[key] = websocket
        print(f"{key} connected")
    def disconnect(self,user_type: str,user_id: str):
        key = f"{user_type}_{user_id}"

        if key in self.active_connections:
            del self.active_connections[key]
        print(f"{key} disconnected")
    async def send_message(self,receiver_type: str,receiver_id: str,data: dict):
        key = f"{receiver_type}_{receiver_id}"
        websocket = self.active_connections.get(key)
        if websocket:
            await websocket.send_json(data)
manager = ConnectionManager()