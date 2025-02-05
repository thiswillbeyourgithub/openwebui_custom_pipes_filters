"""
title: AddMetadata
author: thiswillbeyourightub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
version: 1.0.1
date: 2024-08-29
license: GPLv3
description: A Filter that adds user and other type of metadata to the requests. Useful for langfuse or litellm
openwebui_url: https://openwebui.com/f/qqqqqqqqqqqqqqqqqqqq/addmetadata
"""

from pydantic import BaseModel, Field
from typing import Optional, Callable, Any
import json
from functools import cache

@cache
def load_json_dict(user_value: str) -> dict:
    user_value = user_value.strip()
    if not user_value:
        return {}
    loaded = json.loads(user_value)
    assert isinstance(loaded, dict), f"json is not a dict but '{type(loaded)}'"
    return loaded

@cache
def load_json_list(user_value: str) -> list:
    user_value = user_value.strip()
    if not user_value:
        return []
    loaded = json.loads(user_value)
    assert isinstance(loaded, list), f"json is not a list but '{type(loaded)}'"
    assert all(isinstance(elem, str) for elem in loaded), f"List contained non strings elements: '{loaded}'"
    return loaded


class Filter:
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
        extra_tags: str = Field(
            default='["open-webui"]',
            description="String that when passed through json.loads is a list that will be added as tags to the request.",
        )
        debug: bool = Field(
            default=False, description="True to add emitter prints",
        )

    def __init__(self):
        self.valves = self.Valves()

    async def on_valves_updated(self):
        load_json_dict(self.valves.extra_metadata)
        load_json_list(self.valves.extra_tags)

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
                print(f"AddMetadata filter: inlet: {message}")
            if self.valves.debug:
                await emitter.progress_update(message)
            else:
                await emitter.progress_update("")


        if self.valves.debug:
            await log(f"AddMetadata filter: inlet: __user__ {__user__}")
            await log(f"AddMetadata filter: inlet: body {body}")

        # user
        if self.valves.add_userinfo:
            if "user" in body:
                await log(f"User key already found in body: '{body['user']}'")
                if body["user"] != __user__["name"]:
                    await log(f"User key different than expected: '{body['user']}' vs '{__user__['name']}'")
            new_value = f"{__user__['name']}_{__user__['email']}"
            body["user"] = new_value
            await log(f"Added user metadata '{new_value}'")

            if "metadata" in body:
                body["metadata"]["open-webui_userinfo"] = __user__
            else:
                body["metadata"] = {"open-webui_userinfo": __user__}

        # metadata
        metadata = load_json_dict(self.valves.extra_metadata)
        if metadata:
            if "metadata" in body:
                for k, v in metadata.items():
                    if k in body["metadata"]:
                        if isinstance(v, list) and isinstance(body["metadata"][k], list):
                            body["metadata"][k].extend(v)
                        elif isinstance(body["metadata"][k], list):
                            body["metadata"][k].append(v)
                        elif isinstance(v, list):
                            body["metadata"][k] = [body["metadata"][k]] + v
                    else:
                        body["metadata"][k] = v
                        # await log(f"Extra_metadata of key '{k}' was already present in request. Value before: '{body['metadata'][k]}', value after: '{v}'")
                await log("Updated metadata")
            else:
                body["metadata"] = metadata
                await log("Set metadata")
        else:
            await log("No metadata specified")

        tags = load_json_list(self.valves.extra_tags)
        if tags:
            if "tags" in body:
                body["tags"] += tags
                await log("Updated tags")
            else:
                body["tags"] = tags
                await log("Set tags")
        else:
            await log("No tags specified")

        # also add as langfuse metadata
        body["metadata"]["trace_metadata"] = body["metadata"].copy()

        try:
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
                    await log(f"Failed to json dump the following body keys: {failed} with value '{body[k]}'")
            else:
                raise

        await emitter.success_update("")  # hides the emitter
        return body

    # def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
    #     return body


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

