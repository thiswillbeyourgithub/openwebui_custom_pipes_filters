"""
title: CostTrackingPipe
author: thiswillbeyourgithub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
version: 3.1.1
date: 2024-08-21
license: MIT
description: A pipe function to track user costs and remove 'thinking' blocks
"""

from typing import List, Union, Generator, Iterator, Callable, Any, Optional
from pydantic import BaseModel, Field
import requests
import os
import re
import time
import json

DEFAULT_BASE_URL = "http://127.0.0.1:4000"
DEFAULT_CHAT_MODEL = "litellm_sonnet-3.5"
DEFAULT_TITLE_CHAT_MODEL = "litellm_gpt-4o-mini"


class Pipe:

    class Valves(BaseModel):
        LITELLM_BASE_URL: str = DEFAULT_BASE_URL
        api_keys: Optional[str] = Field(
            default=None,
            description="Dict where keys are litellm users and values are their virtual api keys (a string that will be json loaded as a dict). Leave to None if you want to load from env 'COSTTRACKINGPIPE_API_KEYS'",
        )

    class UserValves(BaseModel):
        enabled: bool = Field(default=True, description="True to enable price counting")
        chat_model: str = Field(
            default=DEFAULT_CHAT_MODEL, description="Chat model to use"
        )
        title_chat_model: str = Field(
            default=DEFAULT_TITLE_CHAT_MODEL,
            description="Model to use to generate titles",
        )

        remove_thoughts: bool = Field(
            default=True, description="True to remove the thoughts block"
        )
        start_thoughts: str = Field(
            default="^``` ?thinking", description="Start of thought block"
        )
        stop_thoughts: str = Field(default="```", description="End of thought block")
        debug: bool = Field(
            default=False,
            description="Set to True to print more info to the docker logs, also to not remove the last emitter message.",
        )

    def __init__(self):
        # You can also set the pipelines that are available in this pipeline.
        # Set manifold to True if you want to use this pipeline as a manifold.
        # Manifold pipelines can have multiple pipelines.
        self.type = "manifold"

        # Optionally, you can set the id and name of the pipeline.
        # Best practice is to not specify the id so that it can be automatically inferred from the filename, so that users can install multiple versions of the same pipeline.
        # The identifier must be unique across all pipelines.
        # The identifier must be an alphanumeric string that can include underscores or hyphens. It cannot contain spaces, special characters, slashes, or backslashes.
        self.id = "cost_tracking_pipe"

        # Optionally, you can set the name of the manifold pipeline.
        self.name = "CostTrackingPipe"

        # Initialize rate limits
        self.valves = self.Valves()
        self.uvalves = self.UserValves()

        self.start_thought = re.compile(self.uvalves.start_thoughts)
        self.stop_thought = re.compile(self.uvalves.stop_thoughts)
        self.pattern = re.compile(
            self.uvalves.start_thoughts + "(.*)?" + self.uvalves.stop_thoughts,
            flags=re.DOTALL | re.MULTILINE,
        )

    async def on_valves_updated(self):
        """This function is called when the valves are updated."""

        # just checking the validity of the api_keys
        if self.valves.api_keys is None:
            assert (
                "COSTTRACKINGPIPE_API_KEYS" in os.environ
            ), "You left the valve api_keys to None but didn't set an env variable COSTTRACKINGPIPE_API_KEYS"
            api_keys = os.environ["COSTTRACKINGPIPE_API_KEYS"]
        else:
            api_keys = self.valves.api_keys
        assert isinstance(
            api_keys, str
        ), f"Expected api_keys to be a str at this point, not {type(api_keys)}"
        try:
            api_keys = json.loads(api_keys)
            assert isinstance(
                api_keys, dict
            ), f"Expected api_keys to be a dict at this point, not {type(api_keys)}"
        except Exception as err:
            raise Exception(f"Error when casting api_keys from str to dict: '{err}'")

        assert "default" in api_keys, f"No 'default' key found in dict: {api_keys}"

    async def pipe(
        self,
        body: dict,
        __user__: dict,
        __event_emitter__: Callable[[dict], Any] = None,
        # this is just to debug if there are breaking changes etc
        *args,
        **kwargs,
    ) -> Union[str, Generator, Iterator]:

        # load the api_keys as a dict
        if self.valves.api_keys is None:
            assert (
                "COSTTRACKINGPIPE_API_KEYS" in os.environ
            ), "You left the valve api_keys to None but didn't set an env variable COSTTRACKINGPIPE_API_KEYS"
            api_keys = os.environ["COSTTRACKINGPIPE_API_KEYS"]
        else:
            api_keys = self.valves.api_keys
        assert isinstance(
            api_keys, str
        ), f"Expected api_keys to be a str at this point, not {type(api_keys)}"
        try:
            api_keys = json.loads(api_keys)
            assert isinstance(
                api_keys, dict
            ), f"Expected api_keys to be a dict at this point, not {type(api_keys)}"
        except Exception as err:
            raise Exception(f"Error when casting api_keys from str to dict: '{err}'")

        assert "default" in api_keys, f"No 'default' key found in dict: {api_keys}"

        # prints and emitter to show progress
        def pprint(message: str) -> str:
            print(f"CostTrackingPipe of '{__user__['name']}': " + str(message))
            return message

        emitter = EventEmitter(__event_emitter__)

        async def prog(message: str) -> None:
            await emitter.progress_update(pprint(message))

        async def succ(message: str) -> None:
            await emitter.success_update(pprint(message))

        async def err(message: str) -> None:
            await emitter.error_update(pprint(message))

        # to know in the future if there are new arguments I could use
        if args or kwargs:
            if args:
                pprint("Received args:" + str(args))
            if kwargs:
                pprint("Received kwargs:" + str(kwargs))

        if self.uvalves.debug:
            pprint(body.keys())
            pprint(body)

        # match the api key
        headers = {}
        await prog("Start")
        username = __user__["name"]
        if not self.uvalves.enabled:
            await prog("Disabled api key matching, will use the default key")
            apikey = api_keys["default"]
            headers["Authorization"] = f"Bearer {apikey}"

        else:
            if username in api_keys:
                apikey = api_keys[username]
                await prog(f"Will use key for {username}")
                headers["Authorization"] = f"Bearer {apikey}"
            else:
                apikey = api_keys["default"]
                headers["Authorization"] = f"Bearer {apikey}"
                # await err(f"Username {username} not found in litellm env keys")
                # raise Exception(f"User not found: {username}")
        body["user"] = username

        try:
            if body["stream"]:
                model = self.uvalves.chat_model
            else:
                # stream disabled is only used for the summary title creator AFAIK
                model = self.uvalves.title_chat_model
            payload = {**body, "model": model, "user": username}

            await prog("Waiting for response")
            r = requests.post(
                url=f"{self.valves.LITELLM_BASE_URL}/v1/chat/completions",
                json=payload,
                headers=headers,
                stream=True,
            )

            r.raise_for_status()
            assert r.status_code == 200, f"Invalid status code: {r.status_code}"

            if body["stream"]:
                await prog("Receiving chunks")
                if (not self.uvalves.remove_thoughts) or (not self.uvalves.enabled):
                    for line in r.iter_lines():
                        yield line
                    return
                buffer = ""
                thought_pattern = re.compile(r"``` ?thinking.*?```", re.DOTALL)
                thought_removed = False

                for line in r.iter_lines():
                    if (
                        not self.uvalves.debug
                        and "start_time" in locals()
                        and time.time() - start_time > 1
                    ):
                        # remove this print after 1s
                        await succ("")
                    if line:
                        line = line.decode("utf-8")
                        if line.startswith("data: "):
                            line = line[6:]  # Remove "data: " prefix
                        if line.strip() == "[DONE]":
                            break
                        try:
                            parsed_line = json.loads(line)
                        except (json.JSONDecodeError, KeyError):
                            continue

                        content = parsed_line["choices"][0]["delta"].get("content", "")
                        if not content:
                            continue

                        if thought_removed:
                            yield content
                            continue
                        buffer += content
                        match = thought_pattern.search(buffer)
                        if match:
                            # Remove the thought block
                            buffer = buffer[: match.start()] + buffer[match.end() :]
                            yield buffer
                            buffer = ""
                            thought_removed = True
                            await succ("Removed thought block")
                            start_time = time.time()

                if not thought_removed:
                    # model didn't produce a thought (for example can happen for the chat title)
                    await succ("Thought block never found")
                    yield buffer
                    buffer = ""

                if buffer:  # Yield any remaining content with finish_reason "stop"
                    yield buffer

            else:  # return the whole text directly
                await prog("Returning directly")
                j = r.json()
                to_yield = j["choices"][0]["message"].get("content", "")
                yield to_yield

            if not self.uvalves.debug:
                await succ("")  # hides it
            return

        except Exception as e:
            await err(f"Error: {e}")
            raise


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

