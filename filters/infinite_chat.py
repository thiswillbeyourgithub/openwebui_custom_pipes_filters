"""
title: InfiniteChat
author: thiswillbeyourgithub
version: 1.0.0
date: 2025-02-21
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
license: GPLv3
description: A filter that keeps chats manageable by retaining only the last N messages
"""

from pydantic import BaseModel, Field
from typing import Optional, Callable, Any


class Filter:
    class Valves(BaseModel):
        priority: int = Field(
            default=0,
            description="Priority level for the filter operations (default 0).",
        )
        debug: bool = Field(
            default=False, 
            description="True to add emitter prints",
        )

    class UserValves(BaseModel):
        keep_messages: int = Field(
            default=2,
            description="Number of most recent messages to keep in the chat",
        )

    def __init__(self):
        self.valves = self.Valves()

    async def on_valves_updated(self):
        pass

    async def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__: Callable[[dict], Any] = None,
        ) -> dict:
        # printer
        emitter = EventEmitter(__event_emitter__)
        async def log(message: str):
            if self.valves.debug:
                print(f"InfiniteChat filter: inlet: {message}")
            await emitter.progress_update(message)

        if self.valves.debug:
            await log(f"InfiniteChat filter: inlet: messages count before: {len(body['messages'])}")

        keep = __user__["valves"].keep_messages
        if keep < 2:
            await log("keep_messages must be at least 2, using default of 2")
            keep = 2
            
        if len(body["messages"]) > keep:
            # Keep only the most recent messages
            body["messages"] = body["messages"][-keep:]
            await log(f"Trimmed chat history to last {keep} messages")

        return body

    def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        return body


class EventEmitter:
    def __init__(self, event_emitter: Callable[[dict], Any] = None):
        self.event_emitter = event_emitter

    async def progress_update(self, description):
        await self.emit(description)

    async def error_update(self, description):
        await self.emit(description, "error", True)

    async def success_update(self, description):
        await self.emit(description, "success", True)

    async def emit(self, description="Unknown State", status="in_progress", done=False):
        if self.event_emitter:
            await self.event_emitter(
                {
                    "type": "status",
                    "data": {
                        "status": status,
                        "description": description,
                        "done": done,
                    },
                }
            )
