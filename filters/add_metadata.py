"""
title: AddMetadata
author: thiswillbeyourightub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
git_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters
version: 1.1.3
date: 2024-04-03
license: GPLv3
description: A Filter that adds user and other type of metadata to the requests. Made for litellm set to use langfuse callbacks.
openwebui_url: https://openwebui.com/f/qqqqqqqqqqqqqqqqqqqq/addmetadata
"""

from pydantic import BaseModel, Field
from typing import Optional, Callable, Any
import json
from functools import cache
from loguru import logger


@cache
def load_json_dict(user_value: str) -> dict:
    user_value = user_value.strip()
    if not user_value:
        return {}
    loaded = json.loads(user_value)
    assert isinstance(loaded, dict), f"json is not a dict but '{type(loaded)}'"
    return loaded


class Filter:
    VERSION: str = "1.1.3"

    class Valves(BaseModel):
        priority: int = Field(
            default=0,
            description="Priority level for the filter operations (default 0).",
        )
        add_userinfo: bool = Field(
            default=True,
            description="True to add the '__user__' dict of openwebui to the request as metadata. Note that 'user' of __user__ is also set as a 'user' metadata",
        )
        extra_metadata: str = Field(
            default='{"source": "open-webui"}',
            description="String that when passed through json.loads is a dict that will be added to the request. If a the value is a list or a value of the metadata is already set then we will append the new value to the list.",
        )
        extra_tags: list = Field(
            default=["open-webui", "add_metadata_filter"],
            description="List as comma separated string that is added as tags to the request.",
        )
        debug: bool = Field(
            default=False,
            description="True to add emitter prints and set debug_langfuse metadata to True",
        )

    def __init__(self):
        self.valves = self.Valves()

    async def on_valves_updated(self):
        load_json_dict(self.valves.extra_metadata)

    async def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__: Callable[[dict], Any] = None,
        __metadata__: Optional[dict] = None,
        __files__: Optional[dict] = None,
        __model__: Optional[dict] = None,
    ) -> dict:
        # printer
        emitter = EventEmitter(__event_emitter__)
        if __metadata__ is None:
            __metadata__ = {}
        if __model__ is None:
            __model__ = {}

        async def log(message: str):
            if self.valves.debug:
                logger.info(f"AddMetadata filter: inlet: {message}")
            if self.valves.debug:
                await emitter.progress_update(message)

        if "metadata" not in body:
            body["metadata"] = {}

        # user
        if self.valves.add_userinfo:
            if "user" in body:
                await log(f"User key already found in body: '{body['user']}'")
                if body["user"] != __user__["name"]:
                    await log(
                        f"User key different than expected: '{body['user']}' vs '{__user__['name']}'"
                    )
            new_value = f"{__user__['name']}_{__user__['email']}"
            body["user"] = new_value
            await log(f"Added user metadata '{new_value}'")

            body["metadata"]["open-webui_userinfo"] = dict(__user__)
            body["metadata"]["trace_user_id"] = new_value

        # tags
        tags = self.valves.extra_tags
        if tags:
            if "tags" in body["metadata"]:
                body["metadata"]["tags"] += tags
                await log("Updated tags")
            else:
                body["metadata"]["tags"] = tags
                await log("Set tags")
            body["metadata"]["tags"] = list(set(body["metadata"]["tags"]))
            await log(f"Tags are now '{body['metadata']['tags']}'")
        else:
            await log("No tags specified")

        # # I don't understand how to make tags work so trying all ways
        body["metadata"]["trace_tags"] = body["metadata"]["tags"]
        body["metadata"]["trace_metadata"] = {"tags": body["metadata"]["tags"]}
        body["metadata"]["update_trace_tags"] = body["metadata"]["tags"]
        body["metadata"]["existing_trace_tags"] = body["metadata"]["tags"]
        body["metadata"]["existing_tags"] = body["metadata"]["tags"]
        body["tags"] = body["metadata"]["tags"]

        # metadata
        # useful reference: https://docs.litellm.ai/docs/observability/langfuse_integration
        body["metadata"]["session_id"] = __metadata__["chat_id"]
        body["metadata"]["generation_name"] = body["messages"][-1]["content"][:100]
        body["metadata"]["generation_id"] = __metadata__["message_id"]
        body["metadata"]["trace_name"] = body["messages"][-1]["content"][:100]
        body["metadata"]["version"] = self.VERSION
        if self.valves.debug:
            body["metadata"]["debug_langfuse"] = True

        metadata = __metadata__.copy()
        metadata.update(load_json_dict(self.valves.extra_metadata))
        if not metadata:
            await log("No metadata specified")
        else:
            body["metadata"].update(metadata)
            await log("Updated metadata")

        # also add as langfuse metadata
        body["metadata"]["trace_metadata"] = body["metadata"].copy()

        try:
            await log("Metadata at the end of the inlet filter:")
            await log(json.dumps(body))

        # fix: some updates of openwebui can crash json dumping, so we filter out the culprit
        except Exception as e:
            if "Object of type " in str(e) and "is not JSON serializable" in str(e):
                failed = []
                for k in list(body.keys()):
                    try:
                        json.dumps(body[k])
                    except Exception:
                        failed.append(k)
                assert failed, f"No culprit key found when json-dumping body: {body}"
                body2 = body.copy()
                for k in failed:
                    body2[k] = str(body2[k])

                await log(json.dumps(body2))
                if self.valves.debug:
                    await log(
                        f"Failed to json dump the following body keys: {failed} with value '{body[k]}'"
                    )
            else:
                raise

        body["extra_body"] = {"metadata": body["metadata"]}

        if self.valves.debug:
            await emitter.success_update("Done")
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

