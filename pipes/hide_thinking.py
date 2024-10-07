"""
title: RemoveThinkingPipe
author: thiswillbeyourgithub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
date: 2024-08-21
version: 1.4.0
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
        litellm_base_url: Optional[str] = Field(
            default=DEFAULT_BASE_URL,
            description="The base url for litellm",
        )
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
        start_thought: str = Field(
            default="``` ?thinking", description="Start of thought block"
        )
        stop_thought: str = Field(default="```", description="End of thought block")
        cache_system_prompt: bool = Field(
            default=True,
            description="Wether to cache the system prompt, if using a claude model",
        )

    class UserValves(BaseModel):
        remove_thoughts: bool = Field(
            default=True, description="True to remove the thoughts block"
        )
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
        # just checking the validity of the api_key
        api_key = self.valves.api_key
        assert isinstance(
            api_key, str
        ), f"Expected api_key to be a str, not {type(api_key)}"
        api_key = api_key.strip()
        assert api_key, "Valve api_key is empty"

        self.start_thought = re.compile(self.valves.start_thought)
        self.stop_thought = re.compile(self.valves.stop_thought)
        self.pattern = re.compile(
            self.valves.start_thought + "(.*)?" + self.valves.stop_thought,
            flags=re.DOTALL | re.MULTILINE,
        )

    async def pipe(
        self,
        body: dict,
        __user__: dict,
        __event_emitter__: Callable[[dict], Any] = None,
        # this is just to debug if there are breaking changes etc
        *args,
        **kwargs,
    ) -> Union[str, Generator, Iterator]:

        # wrap the whole function into a try block to yield the exception
        try:
            self.update_valves()

            apikey = self.valves.api_key

            # prints and emitter to show progress
            def pprint(message: str) -> str:
                self.p(f"'{__user__['name']}': {message}")
                return message

            emitter = EventEmitter(__event_emitter__)
            clear_emitter = not __user__["valves"].debug
            latest_message = ""

            async def prog(message: str) -> None:
                nonlocal latest_message
                if message == latest_message:
                    return
                latest_message = message
                await emitter.progress_update(pprint(message))

            async def succ(message: str) -> None:
                nonlocal latest_message
                if message == latest_message:
                    return
                latest_message = message
                await emitter.success_update(pprint(message))

            async def err(message: str) -> None:
                nonlocal clear_emitter, latest_message
                if message == latest_message:
                    return
                latest_message = message
                clear_emitter = False
                await emitter.error_update(pprint(message))

            # to know in the future if there are new arguments I could use
            if args or kwargs:
                if args:
                    pprint("Received args:" + str(args))
                if kwargs:
                    pprint("Received kwargs:" + str(kwargs))

            if __user__["valves"].debug:
                pprint(body.keys())
                pprint(body)

            if body["stream"]:
                model = self.valves.chat_model
                title = False
                user = f"{__user__['name']}_{__user__['email']}"
            else:
                # stream disabled is only used for the summary title creator AFAIK
                title = True
                model = self.valves.title_chat_model
                user = f"titlecreator_{__user__['name']}_{__user__['email']}"

            # claude prompt caching
            can_be_cached = False
            for w in ["anthropic", "claude", "haiku", "sonnet"]:
                if w in model.lower():
                    can_be_cached = True
                    break
            if self.valves.cache_system_prompt and can_be_cached:
                pprint("Using anthropic's prompt caching")
                for i, m in enumerate(body["messages"]):
                    if m["role"] != "system":
                        continue
                    if isinstance(m["content"], str):
                        sys_prompt = m["content"]
                    elif isinstance(m["content"], list):
                        sys_prompt = ""
                        for ii, mm in enumerate(m["content"]):
                            sys_prompt += mm["text"]
                    elif isinstance(m["content"], dict):
                        sys_prompt = m["content"]["text"]
                    else:
                        raise Exception(f"Unexpected system message: '{m}'")
                    body["messages"][i] = {
                        "role": "system",
                        "content": [
                            {
                                "type": "text",
                                "text": sys_prompt,
                                "cache_control": {"type": "ephemeral"},
                            }
                        ],
                    }
            else:
                pprint("Anthropic caching will not be used for this call")

            # match the api key
            headers = {}
            headers["Authorization"] = f"Bearer {apikey}"

            payload = body.copy()
            payload["model"] = model

            # also sets the user and if it's a titlecreator or not
            if "user" not in body:
                payload["user"] = user
            elif payload["user"] in user:
                payload["user"] = user

            if "metadata" in payload:
                assert (
                    "custom_metadata" not in payload
                ), "Found metadata and custom_metadata in payload"
                payload["custom_metadata"] = payload["metadata"]
                del payload["metadata"]

            if title:
                if "custom_metadata" in payload:
                    if "tags" in payload["custom_metadata"]:
                        assert isinstance(
                            payload["custom_metadata"]["tags"], list
                        ), f"payload['tags'] was not a list but '{type(payload['custom_metadata']['tags'])}"
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
                    print(
                        f"Error: distinct 'session_id' found: '{body['custom_metadata']['session_id']}' in body and '{body['chat_id']}' in body. Keeping the later"
                    )
                    body["custom_metadata"]["session_id"] = body["chat_id"]

            await prog("Waiting for response")
            try:
                r = requests.post(
                    url=f"{self.valves.litellm_base_url}/v1/chat/completions",
                    json=payload,
                    headers=headers,
                    stream=True,
                )
                r.raise_for_status()
            except Exception as e:
                raise Exception(f"Error when creating requests: ") from e
            assert r.status_code == 200, f"Invalid status code: {r.status_code}"

            yielded = ""

            if not title:
                await prog("Receiving chunks")

                # disabled, return all directly
                if not __user__["valves"].remove_thoughts:
                    for line in r.iter_lines():
                        try:
                            content = self.parse_chunk(line)
                        except Exception as e:
                            es = str(e)
                            if es == "DONE":
                                break
                            elif es == "CONTINUE":
                                continue
                            else:
                                raise Exception("Error when parsing chunk: ") from e
                        yielded += content
                        yield content
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

                    try:
                        content = self.parse_chunk(line)
                    except Exception as e:
                        e = str(e)
                        if e == "DONE":
                            break
                        elif e == "CONTINUE":
                            continue
                        else:
                            raise
                    buffer += content

                    match = self.pattern.search(buffer)
                    if match:  # Remove the thought block
                        section = match.group()
                        buffer = buffer.replace(section, "")
                        section = self.start_thought.sub("\n\n<details>\n<summary>Reasonning</summary>\n\n", section)
                        section = self.stop_thought.sub("\n\n</details>\n", section)
                        yielded += section
                        yield section
                        thought_removed += 1
                        await succ(f"Removed {thought_removed} thought block")

                    if buffer:
                        # remove ulterior thought blocks
                        start_match = self.start_thought.search(buffer)
                        if start_match:
                            await prog(
                                f"Waiting for thought n°{thought_removed + 1} to finish"
                            )

                        # TODO: actually the start_thought is not of the same length as its pattern but in most cases it's a good upper bound
                        elif len(buffer) > len_start_thought:
                            to_yield = buffer[:-len_start_thought]
                            buffer = buffer[-len_start_thought:]
                            yielded += to_yield
                            yield to_yield

                if buffer:  # Yield any remaining content with finish_reason "stop"
                    match = self.pattern.search(buffer)
                    if match:
                        section = match.group()
                        buffer = buffer.replace(section, "")
                        section = self.start_thought.sub("\n\n<details>\n<summary>Reasonning</summary>\n\n", section)
                        section = self.stop_thought.sub("\n\n</details>\n", section)
                        yielded += section
                        yield section

                        thought_removed += 1
                        yielded += buffer
                        yield buffer
                        await succ(f"Removed {thought_removed} thought block")

                    elif self.start_thought.search(buffer):
                        await err("It seems a thought was never finished")
                        yielded += buffer
                        yield buffer
                    else:
                        # await succ(f"Was waiting for a buffer bit: {buffer}")
                        yielded += buffer
                        yield buffer

                if not thought_removed:
                    # model didn't produce a thought (for example can happen for the chat title)
                    await err("Thought block never found")

            else:  # return the whole text directly
                await prog("Returning directly")
                j = r.json()
                to_yield = j["choices"][0]["message"].get("content", "")
                yielded += to_yield
                yield to_yield

            assert yielded, "No text to show"

            if clear_emitter:
                await succ("")  # hides it
            return

        except Exception as e:
            if "err" in locals():
                await err(f"Error: {e}")
            else:
                yield f"An error has occured:\n---\n{e}\n---"
            raise

    def parse_chunk(self, line) -> str:
        line = line.decode("utf-8")
        if line.startswith("data: "):
            line = line[6:]  # Remove "data: " prefix
        if line.strip() == "[DONE]":
            raise Exception("DONE")  # triggers a break
        try:
            parsed_line = json.loads(line)
        except (json.JSONDecodeError, KeyError):
            raise Exception("CONTINUE")

        if (
            "error" in parsed_line
            and "message" in parsed_line["error"]
            and parsed_line["error"]["message"]
        ):
            raise Exception(f"Error: {parsed_line['error']['message']}")

        try:
            content = parsed_line["choices"][0]["delta"].get("content", "")
        except KeyError as e:
            raise Exception(
                f"KeyError for parsed_line: '{e}'.\nParsed_line: '{parsed_line}'"
            )

        if not content:
            raise Exception("CONTINUE")
        return content


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

