"""
title: langfuse_filter
author: thiswillbeyourightub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
git_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters
version: 1.0.1
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
from langfuse import Langfuse
from datetime import datetime
from filelock import FileLock

LOCK_FILENAME = "./langfuse_filter.lock"
BUFFER = Path("./langfuse_filter.buffer")
with FileLock(LOCK_FILENAME, timeout=1):
    BUFFER.touch()
    if BUFFER.read_text() == "":
        BUFFER.write_text("{}")

class Filter:
    VERSION="1.0.1"

    class Valves(BaseModel):
        priority: int = Field(
            default=10,
            description="Priority level for the filter operations (default 0).",
        )
        debug: bool = Field(
            default=True,
            description="True to print debug statements",
        )
        langfuse_host: str = Field(
            default='',
            description="langfuse_host",
            required=True,
        )
        langfuse_public_key: str = Field(
            default='',
            description="langfuse_public_key",
            required=True,
        )
        langfuse_secret_key: str = Field(
            default='',
            description="langfuse_secret_key",
            required=True,
        )

    def __init__(self):
        self.valves = self.Valves()
        self.debug = self.valves.debug
        self.lock = FileLock(LOCK_FILENAME, timeout=5)

    async def log(self, message: str, force: bool = False) -> None:
        if self.valves.debug or force:
            print(f"LangfuseFilter: {message}")
        if force:
            await self.emitter.error_update(f"LangfuseFilter: {message}")

    async def __init_langfuse__(self):
        try:
            self.langfuse = Langfuse(
                host="http://" + self.valves.langfuse_host if not self.valves.langfuse_host.startswith("http") else self.valves.langfuse_host,
                public_key=self.valves.langfuse_public_key,
                secret_key=self.valves.langfuse_secret_key,
                # debug=self.valves.debug,  # a bit too verbose
            )
        except Exception as e:
            await self.log(f"Failed to init langfuse: '{e}'", force=True)
            raise Exception(f"Failed to init langfuse: '{e}'", force=True)

    async def inlet(
        self,
        body: dict,
        __metadata__: Optional[dict] = None,
        __event_emitter__: Callable[[dict], Any] = None,
        ) -> dict:
        self.emitter = EventEmitter(__event_emitter__)

        if not hasattr(self, "langfuse"):
            await self.__init_langfuse__()

        chat_id = __metadata__["chat_id"]
        with self.lock:
            content = BUFFER.read_text()
            try:
                buffer = json.loads(content)
                assert isinstance(buffer, dict), f"Not a dict but {type(buffer)}"
            except Exception as e:
                self.log(f"LangfuseFilterInlet: Error when loading json: '{e}'\nBuffer: {content}")
                await self.emitter.error_update(f"LangfuseFilterInlet: Error when loading json: '{e}'\nBuffer: {content}")
                buffer = {}

            if chat_id in buffer:
                self.log(f"INLET ERROR: buffer already contains chat_id '{chat_id}': '{buffer[chat_id]}'", force=True)

            self.log(f"Started timer for chat_id {chat_id}")
            buffer[chat_id] = time.time()
            BUFFER.write_text(json.dumps(buffer))
        return body

    async def outlet(
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
        if not hasattr(self, "langfuse"):
            await self.__init_langfuse__()

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

        model_parameters = self.flatten_dict(__model__)
        metadata["files"] = self.flatten_dict(__files__)

        # await self.log(f"MODEL_INFO: {model_parameters}")

        with self.lock:
            content = BUFFER.read_text()
            try:
                buffer = json.loads(content)
                assert isinstance(buffer, dict), f"Not a dict but {type(buffer)}"
            except Exception as e:
                await self.log(f"LangfuseFilterOutlet: Error when loading json: '{e}'\nBuffer: {content}")
                await self.emitter.error_update(f"LangfuseFilterOutlet: Error when loading json: '{e}'\nBuffer: {content}")
                buffer = {}

            if chat_id not in buffer:
                await self.log(f"OUTLET ERROR: buffer is missing chat_id '{chat_id}'", force=True)
                t_start = None
            else:
                t_start = datetime.fromtimestamp(float(buffer[chat_id]))

            # source: https://langfuse.com/docs/sdk/python/low-level-sdk

            trace = self.langfuse.trace(
                # id=chat_id,
                # name="OpenWebuiLangfuseFilter",
                name = "open-webui_chat-trace",
                input=body["messages"][:-1],
                output=body["messages"][-1],
                metadata=metadata,
                user_id=__user__["name"],
                # session_id=__metadata__["session_id"],
                session_id=chat_id,
                version=self.VERSION,
                tags=["open-webui", "langfuse_filter"],
                public=False,
            )
            span = trace.span(
                # id=__metadata__["message_id"],
                start_time=t_start,
                end_time=t_end,
                name="open-webui-chat-trace-span",
                metadata=metadata,
                input=body["messages"][:-1],
                output=body["messages"][-1],
                version=self.VERSION,
            )
            generation = span.generation(
                # id=__metadata__["message_id"],
                name=messages[-1]["content"][:100],
                start_time=t_start,
                end_time=t_end,
                model= __model__['info']["base_model_id"],
                model_parameters=model_parameters,
                input=body["messages"][:-1],
                output=body["messages"][-1],
                metadata=metadata,
                version=self.VERSION,
            )

            self.langfuse.flush()

            if chat_id in buffer and buffer[chat_id] == t_start:
                del buffer[chat_id]

            BUFFER.write_text(json.dumps(buffer))

        await self.log(f"Done with langfuse with chat_id {chat_id}")
        return body

    def flatten_dict(self, input: dict) -> dict:
        if not isinstance(input, dict):
            return input
        
        result = input.copy()
        while any(isinstance(v, dict) for v in result.values()):
            dict_found = False
            for k, v in list(result.items()):  # Create a list to avoid modification during iteration
                if isinstance(v, dict):
                    dict_found = True
                    # Remove the current key-value pair
                    del result[k]
                    # Flatten and add the nested dictionary items
                    for k2, v2 in v.items():
                        new_key = f"{k}_{k2}"
                        while new_key in result:
                            new_key = new_key + "_"
                        result[new_key] = v2
                    break
                else:
                    # Handle non-dictionary values
                    if isinstance(v, list):
                        try:
                            result[k] = json.dumps(v)  # langfuse hates lists
                        except Exception:
                            result[k] = str(v)
                    else:
                        try:
                            json.dumps(v)  # Just test if serializable
                        except Exception:
                            result[k] = str(v)

        return result


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

