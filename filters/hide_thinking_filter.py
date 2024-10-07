"""
title: Thinking Filter
author: thiswillbeyourgithub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters
version: 0.5
description: the inlet removes thinking xml tags, the outlet makes sure they appear as a <details> xml tag
"""

import re
from pydantic import BaseModel, Field
from typing import Optional


class Filter:
    class Valves(BaseModel):
        verbose: bool = Field(
            default=True, description="Verbosity"
        )
        start_thought_token: str = Field(
            default="^``` ?thinking", description="The start of thougt token."
        )
        end_thought_token: str = Field(
            default="```", description="The end of thought token."
        )

    def __init__(self):
        self.valves = self.Valves()
        self.p("Init start")

        self.start_thought = re.compile(self.valves.start_thought_token)
        self.end_thought = re.compile(self.valves.end_thought_token)

        self.pattern = re.compile(
            rf"{self.valves.start_thought_token}(.*?){self.valves.end_thought_token}",
            flags=re.DOTALL | re.MULTILINE,
        )
        self.converted_pattern = re.compile(r"<details>\s*<summary>Reasonning</summary>.*?</details>")
        self.p("Init done")
        pass

    def remove_thought(self, text: str) -> str:
        "remove thoughts"
        self.p("Removing thought: start")
        if not (self.pattern.search(text) or self.converted_pattern.search(text)):
            self.p("No thought to remove in text")
            return text
        assert text.strip(), "Received empty text"
        step1 = self.pattern.sub("", text).strip()
        assert step1, "Empty text after step 1 of thought removal"
        step2 = self.converted_pattern.sub("", text).strip()
        assert step2, "Empty text after step 2 of thought removal"
        self.p("Removing thought: done")
        return step2

    def hide_thought(self, text: str) -> str:
        "put the thoughts in <details> tags"
        self.p("Hiding thought: start")
        match = self.pattern.search(text)
        if not match:
            self.p(f"No thought to hide in text")
            return text
        section = match.group()
        section = self.start_thought.sub("<details>\n<summary>Reasonning</summary>\n\n", section)
        section = self.stop_thought.sub("\n\n</details>\n", section)
        newtext = text.replace(match.group(), section)
        self.p("Hiding thought: done")
        return newtext

    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        "reduce token count by removing thoughts in the previous messages"
        self.p("inlet start")
        for im, m in enumerate(body["messages"]):
            if "content" in m:
                if isinstance(m["content"], list):
                    for im2, m2 in enumerate(m["content"]):
                        if "content" in m2:
                            body["messages"][im]["content"][im2]["content"] = self.remove_thought(m2["content"])
                        elif "text" in m2:
                            body["messages"][im]["content"][im2]["text"] = self.remove_thought(m2["text"])
                else:
                    body["messages"][im]["content"] = self.remove_thought(m["content"])
        self.p("inlet done")
        return body

    def p(self, message: str) -> None:
        "log message to logs"
        if self.valves.verbose:
            print("ThinkingFilter:outlet:" + message)

    async def outlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
    ) -> dict:
        self.p(f"outlet:{__user__}")
        # self.p(f"outlet:content:{body['messages'][-1]['content']}")
        # self.p(f"outlet:user:{__user__}")
        # self.p(str(body)

        last_message = body["messages"][-1]["content"]

        if isinstance(last_message, list):
            for im2, m2 in enumerate(last_message):
                if "content" in m2:
                    body["messages"][-1]["content"][im2]["content"] = self.hide_thought(m2["content"])
                elif "text" in m2:
                    body["messages"][-1]["content"][im2]["text"] = self.hide_thought(m2["text"])

        elif isinstance(last_message, str):
            last_message = last_message["content"].strip()
            old = last_message.strip()
            new = self.hide_thought(old).strip()
            if old != new:
                self.p("outlet:Hid a thought")
                body["messages"][-1]["content"] = new
            else:
                self.p("outlet:Unmodified text")
            if (not new) and old:
                body["messages"][-1]["content"] = old
                self.p("outlet:Empty after filtering, returning the whole thing")
        else:
            self.p(f"outlet: Unexpected type of last_message: {type(last_message)}")

        return body


