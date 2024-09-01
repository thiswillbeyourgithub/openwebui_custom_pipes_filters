"""
title: Chat Info Filter Pipeline
author: changchiyou (fork by thiswillbeyourigthub)
date: 2024-09-01
version: 1.0
license: MIT
description: A filter pipeline that preprocess form data before requesting chat completion with LiteLLM.
requirements:
funding_url: https://github.com/open-webui/pipelines/discussions/198#discussioncomment-10348421
"""
from typing import List, Optional
from pydantic import BaseModel, Field
import json


class Pipeline:
    class Valves(BaseModel):
        pipelines: List[str] = []
        priority: int = 0
        tags: str = Field(default="", description="A string that when parsed as json is a list of tags to add to each request")
        extra_metadata: str = Field(
            default="",
            description="A string that when parsed as json is a dict"
        )

    def __init__(self):
        self.type = "filter"
        self.name = "Chat Info Filter"

        # Initialize
        self.valves = self.Valves(
            **{
                "pipelines": ["*"],  # Connect to all pipelines
                "priority": 0
            }
        )

        self.chat_generations = {}

    async def on_startup(self):
        print(f"on_startup:{__name__}")

    async def on_shutdown(self):
        print(f"on_shutdown:{__name__}")
        pass

    async def on_valves_updated(self):
        print(f"on_valves_updated:{__name__}")
        if isinstance(self.valves.extra_metadata, str):
            try:
                json.loads(self.valves.extra_metadata)
            except Exception as err:
                raise Exception(f"Failed to parse extra_metadata as json dict: '{err}'")

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        print(f"inlet:{__name__}")

        # move 'metadata' into 'custom_metadata' if possible
        if "metadata" in body:
            if "custom_metadata" not in body:
                body["custom_metadata"] = body["metadata"]
                del body["metadata"]
            else:
                print(f"Error: found 'metadata' and 'custom_metadata' in body as keys")

        # add session_id for langfuse, reusing open-webui's chat_id
        if "custom_metadata" not in body:
            body["custom_metadata"] = {
                "session_id": body['chat_id']
            }
        else:
            if "session_id" not in body["custom_metadata"]:
                body["custom_metadata"]["session_id"] = body["chat_id"]
            elif body["custom_metadata"]["session_id"] != body["chat_id"]:
                print(f"Error: distinct 'session_id' found: '{body['custom_metadata']['session_id']}' in body and '{body['chat_id']}' in body. Keeping the later")
                body["custom_metadata"]["session_id"] = body["chat_id"]

        # same with user id
        if user := user if user else body.get("user"):
            body["custom_metadata"]["trace_user_id"] = f'{user["name"]} / {user["email"]}'
        else:
            print(f"Error: user & body[\"user\"] are both None")

        # add missing tags
        if self.valves.tags.strip():
            if "tags" in body["custom_metadata"]:
                for t in json.loads(self.valves.tags):
                    if t not in body["custom_metadata"]["tags"]:
                        body["custom_metadata"]["tags"].append(t)
            else:
                body["custom_metadata"]["tags"] = self.valves.tags
            body["custom_metadata"]["tags"] = sorted(body["custom_metadata"]["tags"])

        # add extra metadata
        if self.valves.extra_metadata.strip():
            em = json.loads(self.valves.extra_metadata)
            for k, v in em.items():
                if k in body["custom_metadata"] and v != body["custom_metadata"][k]:
                    print(f"Error: extra_metadata '{k}' is already present and of different value")
                body["custom_metadata"][k] = v

        return body
