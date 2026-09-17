# Copyright (C) CVAT.ai Corporation
#
# SPDX-License-Identifier: MIT

import asyncio
import json
import logging
from typing import Dict, Optional, Set
from urllib.parse import parse_qs

logger = logging.getLogger("cvat.apps.test.websocket")


class ConnectionGroupManager:
    """
    Manages active WebSocket connections grouped by task_id or job_id room.
    Ensures safe broadcast and cleanup of terminated connections.
    """

    def __init__(self):
        self._rooms: Dict[str, Set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    def _get_room_key(self, task_id: Optional[int], job_id: Optional[int]) -> str:
        if job_id:
            return f"job_{job_id}"
        if task_id:
            return f"task_{task_id}"
        return "global"

    async def register(self, task_id: Optional[int], job_id: Optional[int], queue: asyncio.Queue) -> str:
        room = self._get_room_key(task_id, job_id)
        async with self._lock:
            if room not in self._rooms:
                self._rooms[room] = set()
            self._rooms[room].add(queue)
            logger.info(f"WebSocket client registered for room {room}. Total in room: {len(self._rooms[room])}")
        return room

    async def unregister(self, room: str, queue: asyncio.Queue):
        async with self._lock:
            if room in self._rooms and queue in self._rooms[room]:
                self._rooms[room].remove(queue)
                if not self._rooms[room]:
                    del self._rooms[room]
                logger.info(f"WebSocket client unregistered from room {room}")

    async def broadcast_to_room(self, room: str, payload: dict):
        async with self._lock:
            queues = list(self._rooms.get(room, set()))
            # Also send to global subscribers
            if room != "global" and "global" in self._rooms:
                queues.extend(list(self._rooms["global"]))

        message_str = json.dumps(payload)
        for q in queues:
            try:
                q.put_nowait(message_str)
            except Exception as e:
                logger.warning(f"Error queueing WebSocket message: {e}")


channel_manager = ConnectionGroupManager()
_main_event_loop: Optional[asyncio.AbstractEventLoop] = None


def set_main_event_loop(loop: asyncio.AbstractEventLoop):
    global _main_event_loop
    _main_event_loop = loop


def broadcast_analytics_update(task_id: Optional[int] = None, job_id: Optional[int] = None) -> int:
    """
    Synchronous / thread-safe entry point to trigger an analytics update broadcast.
    Can be invoked from Django signals, REST views, or celery tasks.
    """
    from .services import AnalyticsService

    try:
        data = AnalyticsService.get_class_wise_counts(task_id=task_id, job_id=job_id)
    except Exception as e:
        logger.error(f"Failed to aggregate class-wise counts for broadcast: {e}")
        return 0

    room = channel_manager._get_room_key(task_id, job_id)
    payload = {
        "event": "CLASS_COUNTS_UPDATED",
        "room": room,
        "data": data,
    }

    global _main_event_loop
    if _main_event_loop and _main_event_loop.is_running():
        asyncio.run_coroutine_threadsafe(
            channel_manager.broadcast_to_room(room, payload), _main_event_loop
        )
    else:
        # If in a standalone sync thread without global loop, create task if loop exists
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(channel_manager.broadcast_to_room(room, payload))
        except Exception:
            pass

    return len(channel_manager._rooms.get(room, []))


async def websocket_analytics_handler(scope, receive, send):
    """
    ASGI 3.0 WebSocket handler for real-time analytics streaming.
    Route: /ws/test/analytics/?task_id=<id>&job_id=<id>
    """
    set_main_event_loop(asyncio.get_running_loop())

    query_string = scope.get("query_string", b"").decode("utf-8")
    params = parse_qs(query_string)

    task_id = int(params["task_id"][0]) if "task_id" in params and params["task_id"][0].isdigit() else None
    job_id = int(params["job_id"][0]) if "job_id" in params and params["job_id"][0].isdigit() else None

    # 1. Accept WebSocket handshake
    await send({"type": "websocket.accept"})

    # Send initial connection acknowledgment
    await send({
        "type": "websocket.send",
        "text": json.dumps({
            "event": "CONNECTED",
            "status": "connected",
            "task_id": task_id,
            "job_id": job_id,
            "message": "Real-time analytics stream established successfully.",
        }),
    })

    # 2. Immediately send current data
    from .services import AnalyticsService
    if task_id or job_id:
        try:
            initial_data = AnalyticsService.get_class_wise_counts(task_id=task_id, job_id=job_id)
            await send({
                "type": "websocket.send",
                "text": json.dumps({
                    "event": "INITIAL_DATA",
                    "data": initial_data,
                }),
            })
        except Exception as e:
            logger.warning(f"Could not load initial analytics for WebSocket: {e}")

    # 3. Register client in room
    queue: asyncio.Queue = asyncio.Queue()
    room = await channel_manager.register(task_id, job_id, queue)

    # 4. Concurrently listen for outgoing messages from queue and incoming from client
    async def sender_task():
        while True:
            try:
                msg = await queue.get()
                await send({"type": "websocket.send", "text": msg})
                queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error sending message down WebSocket: {e}")
                break

    sender = asyncio.create_task(sender_task())

    try:
        while True:
            event = await receive()
            event_type = event.get("type")

            if event_type == "websocket.disconnect":
                break

            if event_type == "websocket.receive":
                text = event.get("text", "")
                try:
                    payload = json.loads(text) if text else {}
                    action = payload.get("action", "")

                    if action == "ping":
                        await send({
                            "type": "websocket.send",
                            "text": json.dumps({"event": "pong", "timestamp": payload.get("timestamp")}),
                        })
                    elif action == "refresh":
                        if task_id or job_id:
                            refreshed = AnalyticsService.get_class_wise_counts(task_id=task_id, job_id=job_id)
                            await send({
                                "type": "websocket.send",
                                "text": json.dumps({"event": "CLASS_COUNTS_UPDATED", "data": refreshed}),
                            })
                except Exception as ex:
                    logger.warning(f"Error processing client message: {ex}")

    finally:
        sender.cancel()
        await channel_manager.unregister(room, queue)
