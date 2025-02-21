"""
title: langfuse_filter
author: thiswillbeyourightub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
git_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters
version: 1.0.0
date: 2025-02-21
license: GPLv3
description: A Filter that prints arguments as they go through it
openwebui_url: https://openwebui.com/f/qqqqqqqqqqqqqqqqqqqq/langfuse_filter
---
requirements: langfuse>=2.59.3
---
"""

import os
from pydantic import BaseModel, Field
from typing import Optional, Callable, Any
from langfuse.decorators import observe, langfuse_context

def p(message: str) -> None:
    print(f"LangfuseFilter: {message}")

def waiter(**kwargs):
    while True:
        time.sleep(1)

class Singleton:
    _instance = None
    _cnt = None
    buffer = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # This will run multiple times if constructor is called multiple times
        if self._cnt is None:
            self._cnt = 0
        if self.buffer is None:
            self.buffer = {}
        self._cnt += 1
        p(f"Singleton count: {self._cnt}")

holder = Singleton()

class Filter:
    class Valves(BaseModel):
        priority: int = Field(
            default=10,
            description="Priority level for the filter operations (default 0).",
        )
        debug: bool = Field(
            default=True,
            description="True to print debug statements",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.debug = self.valves.debug

    async def log(self, message: str, force: bool = False) -> None:
        if self.valves.debug or force:
            print(f"LangfuseFilter: {message}")
        if force:
            await self.emitter.error_update(f"LangfuseFilter: {message}")


    async def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __metadata__: Optional[dict] = None,
        __model__: Optional[dict] = None,
        __files__: Optional[list] = None,
        __event_emitter__: Callable[[dict], Any] = None,
        ) -> dict:
        self.emitter = EventEmitter(__event_emitter__)
        if not "LANGFUSE_HOST" in os.environ:
            self.log("INLET ERROR: LANGFUSE_HOST not in env", force=True)
        if not "LANGFUSE_PUBLIC_KEY" in os.environ:
            self.log("INLET ERROR: LANGFUSE_PUBLIC_KEY not in env", force=True)
        if not "LANGFUSE_SECRET_KEY" in os.environ:
            self.log("INLET ERROR: LANGFUSE_SECRET_KEY not in env", force=True)
        chat_id = __metadata__["chat_id"]
        if chat_id in holder.buffer:
            self.log(f"INLET ERROR: holder already contains chat_id '{chat_id}': '{holder.buffer[chat_id]}'", force=True)

        dec = observe(as_type="generation")
        self.log(f"Entered context for chat_id {chat_id}")
        holder.buffer[chat_id] = context
        return body

    def outlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __metadata__: Optional[dict] = None,
        __model__: Optional[dict] = None,
        __files__: Optional[list] = None,
        __event_emitter__: Callable[[dict], Any] = None,
        ) -> dict:
        self.emitter = EventEmitter(__event_emitter__)
        chat_id = __metadata__["chat_id"]
        if chat_id not in holder.buffer:
            self.log(f"OUTLET ERROR: holder is missing chat_id '{chat_id}'", force=True)
        else:
            context = holder.buffer[chat_id]
            context.__exit__(None, None, None)
            del holder.buffer[chat_id]
        self.log(f"Exited context for chat_id {chat_id}")
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

