# WebSocket

## Endpoint

```
ws://127.0.0.1:<port>/ws/session/<session_id>
```

## Connection

1. Client connects with the correct session ID
2. Server accepts and adds client to `_ws_clients` list
3. Server replays recent events (from `since` offset)
4. Client can send `{"since": <offset>}` to request more events
5. Server broadcasts all new events in real-time

## Message Types

Server → Client:
- `goal_set` — goal was submitted
- `goal_result` — goal execution completed
- `goal_cancelled` — goal was cancelled
- `session_stopped` — session was stopped
- `session_resumed` — session was resumed
- `events_replayed` — replay completed with count
- Any event from `EventLog.emit()` (tool_call_started, council_started, etc.)

## Disconnection

- `WebSocketDisconnect` is caught silently
- Client is removed from `_ws_clients` list
- No reconnection logic (client should reconnect)

## Timeout

WebSocket sends have a 1.5-second timeout. Dead clients are removed from the broadcast list.
