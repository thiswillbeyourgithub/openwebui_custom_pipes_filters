"""
title: WarnIfLongChat
author: thiswillbeyourgithub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
version: 1.0.0
date: 2024-08-29
license: GPLv3
description: A filter that adds a soft and hard limit to the number of messages in a chat.
"""

from pydantic import BaseModel, Field
from typing import Optional, Callable, Any
import time


class Filter:
    class Valves(BaseModel):
        priority: int = Field(
            default=9,
            description="Priority level for the filter operations (default 9).",
        )
        number_of_message: int = Field(
            default=20,
            description="Number of message when to start warning the user",
        )
        number_of_message_hard_limit: int = Field(
            default=50,
            description="Above that many messages, flat out refuse",
        )
        debug: bool = Field(
            default=False, description="True to add emitter prints",
        )

    def __init__(self):
        self.valves = self.Valves()

    async def on_valves_updated(self):
        assert self.valves.number_of_message > 2, "number_of_message has to be more than 2"
        assert self.valves.number_of_message_hard_limit > 5, "number_of_message_hard_limit has to be more than 5"
        assert self.valves.number_of_message_hard_limit > self.valves.number_of_message, "number_of_message_hard_limit has to be higher than number_of_message"

    async def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__: Callable[[dict], Any] = None,
        ) -> dict:
        # printer
        emitter = EventEmitter(__event_emitter__)
        async def log(message: str, error: bool = False):
            if self.valves.debug:
                print(f"WarnIfLongChat filter: inlet: {message}")
            if error:
                em = emitter.error_update
            else:
                em = emitter.progress_update
            await em(message)

        if self.valves.debug:
            await log(f"WarnIfLongChat filter: inlet: __user__ {__user__}")
            await log(f"WarnIfLongChat filter: inlet: body {body}")


        if len(body["messages"]) > self.valves.number_of_message_hard_limit:
            await log(f"I refuse to answer to chats with more than {self.valves.number_of_message_hard_limit} messages", error=True)
            raise Exception(f"I refuse to answer to chats with more than {self.valves.number_of_message_hard_limit} messages")

        elif len(body["messages"]) > self.valves.number_of_message:
            await log(f"Tips: don't use more messages than {self.valves.number_of_message} in a single chat, create new chats instead.", error=True)
            if len(body["messages"]) == self.valves.number_of_message:
                time.sleep(5)
            else:
                time.sleep(1)

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

