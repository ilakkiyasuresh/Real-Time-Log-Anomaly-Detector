from fastapi import WebSocket


class Hub:
    """Keeps the set of connected dashboards and broadcasts JSON to all of them."""

    def __init__(self):
        self.clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket, snapshot: dict):
        await ws.accept()
        self.clients.add(ws)
        # A new tab gets recent history immediately instead of an empty screen.
        await ws.send_json({"type": "snapshot", "data": snapshot})

    def disconnect(self, ws: WebSocket):
        self.clients.discard(ws)

    async def broadcast(self, msg: dict):
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_json(msg)
            except Exception:                # closed tab, network drop
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)
