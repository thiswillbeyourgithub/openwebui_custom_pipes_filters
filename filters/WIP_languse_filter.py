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
requirements: langfuse>=2.59.3,filelock
---
"""

from pathlib import Path
import os
import time
import json
from pydantic import BaseModel, Field
from typing import Optional, Callable, Any, List
from langfuse.decorators import observe, langfuse_context
from datetime import datetime
from filelock import Timeout, FileLock

LOCK_FILENAME="./langfuse_filter.lock"
BUFFER=Path("./langfuse_filter.buffer")

class Filter:
    VERSION="1.0.0"

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
        self.lock = FileLock(LOCK_FILENAME,timeout=1)


    async def log(self, message: str, force: bool = False) -> None:
        if self.valves.debug or force:
            print(f"LangfuseFilter: {message}")
        if force:
            await self.emitter.error_update(f"LangfuseFilter: {message}")

    def flatten_dict(self, input: dict) -> dict:
        input = input.copy()
        while any(isinstance(mp, dict) for mp in input):
            to_add = {}
            for k, v in input.items():
                if isinstance(v, dict):
                    to_add.update(v)
                    break
            del input[k]
            for k2, v2 in to_add.items():
                if k2 in input:
                    k3 = f"{k}_{k2}"
                    while k3 in input:
                        k3 = k3 + "_"
                    input[k3] = v2
                else:
                    input[k2] = v2
        return input


    async def inlet(
        self,
        body: dict,
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
        with self.lock:
            try:
                content = BUFFER.read_text()
                buffer = json.loads(content)
                assert isinstance(buffer, dict), f"Not a dict but {type(buffer)}"
            except Exception as e:
                self.log(f"LangfuseFilterInlet: Error when loading json: '{e}'\nBuffer: {content}")
                await self.emitter.error_update(f"LangfuseFilterInlet: Error when loading json: '{e}'\nBuffer: {content}")
                buffer = {}

            if chat_id in buffer:
                self.log(f"INLET ERROR: holder already contains chat_id '{chat_id}': '{holder.buffer[chat_id]}'", force=True)

            self.log(f"Started timer for chat_id {chat_id}")
            buffer[chat_id] = time.time()
            BUFFER.write_text(json.dumps(buffer))
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
        t_end = datetime.now()
        self.emitter = EventEmitter(__event_emitter__)
        chat_id = __metadata__["chat_id"]

        metadata={
            "ow_message_id": __metadata__["message_id"],
            "ow_session_id":__metadata__["session_id"],
            "ow_user_id": __user__["id"],
            "ow_user_name": __user__["name"],
            "ow_user_mail": __user__["email"],
            "ow_model_name": __model__['info']["id"],
            "ow_base_model_id": __model__['info']["base_model_id"],
        }
        flat_metadata = self.flatten_dict(__metadata__)
        for k, v in flat_metadata.items():
            if v not in metadata.values():
                metadata["ow_" + k] = v

        model_parameters = self.flatten_dict(___model___)
        files = self.flatten_dict(__files__)

        with self.lock:
            try:
                content = BUFFER.read_text()
                buffer = json.loads(content)
                assert isinstance(buffer, dict), f"Not a dict but {type(buffer)}"
            except Exception as e:
                self.log(f"LangfuseFilterOutlet: Error when loading json: '{e}'\nBuffer: {content}")
                await self.emitter.error_update(f"LangfuseFilterOutlet: Error when loading json: '{e}'\nBuffer: {content}")
                buffer = {}

            if chat_id not in buffer:
                self.log(f"OUTLET ERROR: holder is missing chat_id '{chat_id}'", force=True)
                t_start = None
            else:
                t_start = datetime.fromtimestamp(float(buffer[chat_id]))

            @observe(as_type="generation")
            def the_call(messages: List[dict]):
                """
                source: https://langfuse.com/docs/sdk/python/low-level-sdk
                """
                langfuse_context.update_current_trace(
                    # name="OpenWebuiLangfuseFilter",
                    name=messages[-1]["content"][:100],

                    id= __metadata__["message_id"],
                    session_id=__metadata__["session_id"],
                    chat_id=chat_id,
                    user_id=__user__["name"],
                    model= __model__['info']["base_model_id"],
                    input=messages,
                    output=body["messages"][-1],

                    model_parameters=model_parameters,
                    metadata=metadata,

                    tags=["open-webui", "langfuse_filter"],

                    public=False,
                    version=self.VERSION,


                    start_time=t_start,
                    end_time=t_end,
                )
                # return the assistant messsage
                return body["messages"][-1]

            # send every messages except the assisstant answer
            the_call(body["messages"][:-1])

            if chat_id in buffer and buffer[chat_id] == t_start:
                del buffer[chat_id]

            BUFFER.write_text(json.dumps(buffer))

        self.log(f"Done with langfuse with chat_id {chat_id}")
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

