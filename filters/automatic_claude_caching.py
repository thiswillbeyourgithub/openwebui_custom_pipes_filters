"""
title: Automatic Claude Caching Filter
author: thiswillbeyourgithub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters
date: 2024-10-11
version: 0.0
description: the inlet is used to automatically replace the system prompt by a cached system prompt.
license: GPLv3
"""

from pydantic import BaseModel, Field
from typing import Optional


class Filter:
    class Valves(BaseModel):
        verbose: bool = Field(
            default=True, description="Verbosity"
        )
        cache_system_prompt: bool = Field(
            default=True,
            description="True to automatically cache the system prompt"
        )

    def __init__(self):
        self.valves = self.Valves()
        self.p("Init:start")
        self.p("Init:done")
        pass

    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        "reduce token count by removing thoughts in the previous messages"
        self.p("inlet:start")

        if not self.valves.cache_system_prompt:
            self.p("inlet: disabled by valves")
            return body

        self.p("inlet: Using anthropic's prompt caching")
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

    def p(self, message: str) -> None:
        "log message to logs"
        if self.valves.verbose:
            print("AutomaticClaudeCachingFilter:outlet:" + str(message))

