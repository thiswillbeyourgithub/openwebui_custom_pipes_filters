"""
title: RemoveThinkingPipe
author: thiswillbeyourgithub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
date: 2024-08-21
version: 1.1.1
license: GPLv3
description: A pipe function remove thinking blocks
"""

from typing import Union, Generator, Iterator, Callable, Any, Optional
from pydantic import BaseModel, Field
import requests
import re
import json

DEFAULT_BASE_URL = "http://127.0.0.1:4000"
DEFAULT_CHAT_MODEL = "litellm_sonnet-3.5"
DEFAULT_TITLE_CHAT_MODEL = "litellm_gpt-4o-mini"


class Pipe:

    class Valves(BaseModel):
        LITELLM_BASE_URL: str = DEFAULT_BASE_URL
        api_key: Optional[str] = Field(
            default=None,
            description="A litellm API api key",
        )
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
        start_thought: str = Field(
            default="``` ?thinking", description="Start of thought block"
        )
        stop_thought: str = Field(default="```", description="End of thought block")
        cache_system_prompt: bool = Field(default=True, description="Wether to cache the system prompt, if using a claude model")
        debug: bool = Field(
            default=False,
            description="Set to True to print more info to the docker logs, also to not remove the last emitter message.",
        )

    def __init__(self):
        self.id = "RemoveThinkingPipe"
        self.name = "RemoveThinkingPipe"

        # Initialize rate limits
        self.valves = self.Valves()

        self.start_thought = re.compile(self.valves.start_thought)
        self.stop_thought = re.compile(self.valves.stop_thought)
        self.pattern = re.compile(
            self.valves.start_thought + "(.*)?" + self.valves.stop_thought,
            flags=re.DOTALL | re.MULTILINE,
        )

    def p(self, message: str) -> str:
        "simple printer"
        print(f"{self.name}: {message}")
        return message

    def update_valves(self):
        """This function is called when the valves are updated."""
        self.p("Updating valves")

        # just checking the validity of the api_key
        api_key = self.valves.api_key
        assert isinstance(
            api_key, str
        ), f"Expected api_key to be a str, not {type(api_key)}"
        api_key = api_key.strip()
        assert api_key, "Api_key is empty"

        self.start_thought = re.compile(self.valves.start_thought)
        self.stop_thought = re.compile(self.valves.stop_thought)
        self.pattern = re.compile(
            self.valves.start_thought + "(.*)?" + self.valves.stop_thought,
            flags=re.DOTALL | re.MULTILINE,
        )
        self.p("Done updating valves")


    async def pipe(
        self,
        body: dict,
        __user__: dict,
        __event_emitter__: Callable[[dict], Any] = None,
        # this is just to debug if there are breaking changes etc
        *args,
        **kwargs,
    ) -> Union[str, Generator, Iterator]:

        self.update_valves()

        apikey = self.valves.api_key

        # prints and emitter to show progress
        def pprint(message: str) -> str:
            self.p(f"'{__user__['name']}': {message}")
            return message

        emitter = EventEmitter(__event_emitter__)
        clear_emitter = not self.valves.debug

        async def prog(message: str) -> None:
            await emitter.progress_update(pprint(message))

        async def succ(message: str) -> None:
            await emitter.success_update(pprint(message))

        async def err(message: str) -> None:
            nonlocal clear_emitter
            clear_emitter = False
            await emitter.error_update(pprint(message))

        # to know in the future if there are new arguments I could use
        if args or kwargs:
            if args:
                pprint("Received args:" + str(args))
            if kwargs:
                pprint("Received kwargs:" + str(kwargs))

        if self.valves.debug:
            pprint(body.keys())
            pprint(body)

        # if self.valves.cache_system_prompt:
        #     for i, m in enumerate(body["messages"]):
        #         if m["role"] != "system":
        #             continue
        #         if isinstance(m["content"], str):
        #             body["messages"][i] = [{
        #                 "role": "system",
        #                 "type": "text",
        #                 "text": m["content"],
        #                 "cache_control": {"type": "ephemeral"}
        #             }]
        #         elif isinstance(m["content"], list):
        #             for ii, mm in enumerate(m["content"]):
        #                 m["content"][ii]["cache_control"] = {"type": "ephemeral"}
        #             body["messages"][i]["content"] = m["content"]
        #         elif isinstance(m["content"], dict):
        #             body["messages"][i]["content"]["cache_control"] = {"type": "ephemeral"}
        #         else:
        #             raise Exception(f"Unexpected system message: '{m}'")

        # match the api key
        headers = {}
        headers["Authorization"] = f"Bearer {apikey}"
        payload = body.copy()

        # if self.valves.cache_system_prompt:
        #     headers["extra_headers"] = "anthropic-beta: prompt-caching-2024-07-31"

        try:
            if body["stream"]:
                model = self.valves.chat_model
                title = False
                user = f"{__user__['name']}_{__user__['email']}"
            else:
                # stream disabled is only used for the summary title creator AFAIK
                title = True
                model = self.valves.title_chat_model
                user = f"titlecreator_{__user__['name']}_{__user__['email']}"
            payload["model"] = model

            # also sets the user and if it's a titlecreator or not
            if "user" not in body:
                payload["user"] = user
            elif payload["user"] in user:
                payload["user"] = user

            if "metadata" in payload:
                assert "custom_metadata" not in payload, f"Found metadata and custom_metadata in payload"
                payload["custom_metadata"] = payload["metadata"]
                del payload["metadata"]

            if title:
                if "custom_metadata" in payload:
                    if "tags" in payload["custom_metadata"]:
                        assert isinstance(payload["custom_metadata"]["tags"], list), f"payload['tags'] was not a list but '{type(payload['custom_metadata']['tags'])}"
                        payload["custom_metadata"]["tags"].append("title_ceator")
                    else:
                        payload["custom_metadata"]["tags"] = ["title_ceator"]
                else:
                    payload["custom_metadata"] = {"tags": ["title_creator"]}


            # add langfuse session_id
            if "custom_metadata" in payload:
                if "session_id" not in body["custom_metadata"]:
                    body["custom_metadata"]["session_id"] = body["chat_id"]
                elif body["custom_metadata"]["session_id"] != body["chat_id"]:
                    print(f"Error: distinct 'session_id' found: '{body['custom_metadata']['session_id']}' in body and '{body['chat_id']}' in body. Keeping the later")
                    body["custom_metadata"]["session_id"] = body["chat_id"]

            await prog("Waiting for response")
            r = requests.post(
                url=f"{self.valves.LITELLM_BASE_URL}/v1/chat/completions",
                json=payload,
                headers=headers,
                stream=True,
            )
            r.raise_for_status()
            assert r.status_code == 200, f"Invalid status code: {r.status_code}"

            discarded = ""

            if not title:
                await prog("Receiving chunks")

                # disabled, return all directly
                if not self.valves.remove_thoughts:
                    for line in r.iter_lines():
                        yield line
                    if clear_emitter:
                        await succ("")  # hides it
                    return

                buffer = ""
                len_start_thought = int(1.5 * len(self.valves.start_thought))

                # remove thoughts
                thought_removed = 0
                for line in r.iter_lines():
                    if not line:
                        continue

                    # parse content
                    line = line.decode("utf-8")
                    if line.startswith("data: "):
                        line = line[6:]  # Remove "data: " prefix
                    if line.strip() == "[DONE]":
                        break
                    try:
                        parsed_line = json.loads(line)
                    except (json.JSONDecodeError, KeyError):
                        continue

                    if "error" in parsed_line and "message" in parsed_line["error"] and parsed_line["error"]["message"]:
                        raise Exception(f"Error: {parsed_line['error']['message']}")

                    try:
                        content = parsed_line["choices"][0]["delta"].get("content", "")
                    except KeyError as e:
                        raise Exception(f"KeyError for parsed_line: '{e}'.\nParsed_line: '{parsed_line}'")

                    if not content:
                        continue
                    buffer += content

                    match = self.pattern.search(buffer)
                    if match:  # Remove the thought block
                        discarded += buffer[: match.start()] + buffer[match.end() :]
                        buffer = buffer[: match.start()] + buffer[match.end() :]
                        thought_removed += 1
                        await succ(f"Removed {thought_removed} thought block")

                    if buffer:
                        # remove ulterior thought blocks
                        start_match = self.start_thought.search(buffer)
                        if start_match:
                            await prog(f"Waiting for thought n°{thought_removed + 1} to finish")

                        # TODO: actually the start_thought is not of the same length as its pattern but in most cases it's a good upper bound
                        elif len(buffer) > len_start_thought:
                            to_yield = buffer[:-len_start_thought]
                            buffer = buffer[-len_start_thought:]
                            yield to_yield

                if buffer:  # Yield any remaining content with finish_reason "stop"
                    if self.pattern.search(buffer):
                        match = self.pattern.search(buffer)
                        buffer = buffer[: match.start()] + buffer[match.end() :]
                        thought_removed += 1
                        yield buffer
                        await succ(f"Removed {thought_removed} thought block")

                    elif self.start_thought.search(buffer):
                        await err("It seems a thought was never finished")
                        yield buffer
                    else:
                        # await succ(f"Was waiting for a buffer bit: {buffer}")
                        yield buffer

                if not thought_removed:
                    # model didn't produce a thought (for example can happen for the chat title)
                    await err("Thought block never found")

            else:  # return the whole text directly
                await prog("Returning directly")
                j = r.json()
                to_yield = j["choices"][0]["message"].get("content", "")
                yield to_yield

            if clear_emitter:
                await succ("")  # hides it
            return

        except Exception as e:
            await err(f"Error: {e}")
            if "discarded" in locals() and discarded:
                yield "An error has occured. Here's the discarded text anyway:\n" + discarded + "\n\nError was: '{e}'"
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

