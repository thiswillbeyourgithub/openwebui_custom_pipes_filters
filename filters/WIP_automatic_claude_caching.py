"""
title: Automatic Claude Caching Filter
author: thiswillbeyourgithub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters
date: 2024-10-11
version: 0.0 (not yet working)
description: the inlet is used to automatically replace the system prompt by a cached system prompt.
license: AGPLv3
"""

import re
from pydantic import BaseModel, Field
from typing import Optional


class Filter:
    class Valves(BaseModel):
        verbose: bool = Field(default=True, description="Verbosity")
        cache_system_prompt: bool = Field(
            default=True, description="True to automatically cache the system prompt"
        )
        regex_model: str = Field(
            default="anthropic|claude|sonnet|haiku|opus",
            description="If that regex matches the model name, we cache the system prompt. Regex flags are IGNORECASE and DOTALL. Leave empty to always try to cache.",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.p("Init:start")
        self.regex_model = re.compile(
            self.valves.regex_model, flags=re.DOTALL | re.IGNORECASE
        )
        self.p("Init:done")
        pass

    def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        # __task__: Optional[dict] = None,
        # __task_body__: Optional[dict] = None,
    ) -> dict:
        "reduce token count by removing thoughts in the previous messages"
        self.p("inlet:start")

        if not self.valves.cache_system_prompt:
            self.p("inlet: disabled by valves")
            return body

        if self.valves.regex_model:
            model = body["model"]
            if not self.regex_model.match(model):
                self.p(
                    f"inlet: Regex for model does not think this model should be cached. Bypassing cachg. Model: '{model}'"
                )
                return body
        # self.p(__task__)
        # self.p(__task_body__)

        if not any(m["role"] == "system" for m in body["messages"]):
            raise Exception(self.p("No system message found in the chat."))

        self.p(f"inlet: Using anthropic's prompt caching for model {model}")
        modified = False
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

            self.p(f"Will use prompt caching for that message: '{sys_prompt}'")
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
            modified = True

        if not modified:
            self.p("inlet: No message were cached!")
        self.p("inlet:done")
        return body

    def p(self, message: str) -> str:
        "log message to logs"
        m = "AutomaticClaudeCachingFilter:outlet:" + str(message)
        if self.valves.verbose:
            print(m)
        return m
