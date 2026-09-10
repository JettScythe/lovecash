from enum import StrEnum


class ConnectionState(StrEnum):
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    DOWN = "down"
