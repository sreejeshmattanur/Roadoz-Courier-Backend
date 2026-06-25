from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active_connections = {}
        
    async def connect(self, user_type: str, user_id: str, websocket: WebSocket):
        await websocket.accept()
        key = f"{user_type}_{user_id}"
        if key not in self.active_connections:
            self.active_connections[key] = []
        self.active_connections[key].append(websocket)
        print(f"{key} connected")
        
    def disconnect(self, user_type: str, user_id: str, websocket: WebSocket = None):
        key = f"{user_type}_{user_id}"
        if key in self.active_connections:
            if websocket and websocket in self.active_connections[key]:
                self.active_connections[key].remove(websocket)
            elif not websocket:
                self.active_connections[key].clear()
                
            if not self.active_connections[key]:
                del self.active_connections[key]
        print(f"{key} disconnected")
        
    def is_online(self, user_type: str, user_id: str) -> bool:
        key = f"{user_type}_{user_id}"
        return key in self.active_connections and len(self.active_connections[key]) > 0
        
    async def broadcast_to_type(self, target_type: str, data: dict):
        prefix = f"{target_type}_"
        dead_sockets = []
        for key, websockets in self.active_connections.items():
            if key.startswith(prefix):
                for ws in websockets:
                    try:
                        await ws.send_json(data)
                    except Exception:
                        dead_sockets.append((key, ws))
                        
        for key, ws in dead_sockets:
            if key in self.active_connections and ws in self.active_connections[key]:
                self.active_connections[key].remove(ws)
                if not self.active_connections[key]:
                    del self.active_connections[key]
    async def send_message(self, receiver_type: str, receiver_id: str, data: dict):
        key = f"{receiver_type}_{receiver_id}"
        websockets = self.active_connections.get(key, [])
        dead_sockets = []
        for ws in websockets:
            try:
                await ws.send_json(data)
            except Exception:
                dead_sockets.append(ws)
                
        if dead_sockets and key in self.active_connections:
            for ws in dead_sockets:
                if ws in self.active_connections[key]:
                    self.active_connections[key].remove(ws)
            if not self.active_connections[key]:
                del self.active_connections[key]
manager = ConnectionManager()