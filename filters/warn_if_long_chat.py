"""
title: WarnIfLongChat
author: thiswillbeyourgithub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
version: 1.1.0
date: 2025-03-23
license: GPLv3
description: A filter that adds a soft and hard limit to the number of messages in a chat.
"""

from pydantic import BaseModel, Field
from typing import Optional, Callable, Any
import time


class Filter:
    VERSION: str = [li for li in __doc__.splitlines() if li.startswith("version: ")][0].split("version: ")[1]

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
        exempted_users: str = Field(
            default="",
            description="Comma-separated list of usernames that are exempted from this filter",
        )

    def __init__(self):
        self.valves = self.Valves()

    async def on_valves_updated(self):
        assert self.valves.number_of_message > 2, "number_of_message has to be more than 2"
        assert self.valves.number_of_message_hard_limit > 5, "number_of_message_hard_limit has to be more than 5"
        assert self.valves.number_of_message_hard_limit > self.valves.number_of_message, "number_of_message_hard_limit has to be higher than number_of_message"
        
        # Validate exempted_users format
        if self.valves.exempted_users:
            exempted_users = [user.strip() for user in self.valves.exempted_users.split(',')]
            if self.valves.debug:
                print(f"Exempted users: {exempted_users}")

    async def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__: Callable[[dict], Any] = None,
        ) -> dict:
        # Check if user is exempted
        if __user__ and "name" in __user__:
            exempted_users = [user.strip() for user in self.valves.exempted_users.split(',') if user.strip()]
            if __user__["name"] in exempted_users:
                return body
            
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
        # Check if user is exempted
        if __user__ and "name" in __user__:
            exempted_users = [user.strip() for user in self.valves.exempted_users.split(',') if user.strip()]
            if __user__["name"] in exempted_users:
                return body
                
        return body


class EventEmitter:
    def __init__(self, event_emitter: Callable[[dict], Any] = None):
        self.event_emitter = event_emitter

    async def progress_update(self, description):
        if self.event_emitter:
            await self.event_emitter({
                "type": "status",
                "data": {
                    "status": "in_progress",
                    "description": description,
                    "done": False,
                },
            })

    async def error_update(self, description):
        if self.event_emitter:
            await self.event_emitter({
                "type": "status",
                "data": {
                    "status": "error",
                    "description": description,
                    "done": True,
                },
            })

    async def success_update(self, description):
        if self.event_emitter:
            await self.event_emitter({
                "type": "status",
                "data": {
                    "status": "success",
                    "description": description,
                    "done": True,
                },
            })

