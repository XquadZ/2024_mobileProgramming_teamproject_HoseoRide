"""WebSocket endpoint for real-time bus location updates."""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.redis_client import redis_client

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/location/{route_id}")
async def ws_bus_location(websocket: WebSocket, route_id: int):
    await websocket.accept()

    pubsub = redis_client.pubsub()
    channel = f"bus:updates:{route_id}"
    await pubsub.subscribe(channel)

    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message["type"] == "message":
                await websocket.send_text(message["data"])
            else:
                # Send heartbeat to detect disconnected clients
                try:
                    await asyncio.wait_for(
                        websocket.send_json({"type": "ping"}),
                        timeout=5.0,
                    )
                except (asyncio.TimeoutError, WebSocketDisconnect):
                    break
                await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected (route=%d)", route_id)
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()


@router.websocket("/ws/location")
async def ws_all_locations(websocket: WebSocket):
    """Subscribe to all route updates."""
    await websocket.accept()

    pubsub = redis_client.pubsub()
    await pubsub.psubscribe("bus:updates:*")

    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message["type"] == "pmessage":
                channel = message["channel"]
                # Extract route_id from channel name
                route_id = channel.split(":")[-1]
                data = json.loads(message["data"])
                data["route_id"] = int(route_id)
                await websocket.send_json(data)
            else:
                try:
                    await asyncio.wait_for(
                        websocket.send_json({"type": "ping"}),
                        timeout=5.0,
                    )
                except (asyncio.TimeoutError, WebSocketDisconnect):
                    break
                await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected (all routes)")
    finally:
        await pubsub.punsubscribe("bus:updates:*")
        await pubsub.aclose()
