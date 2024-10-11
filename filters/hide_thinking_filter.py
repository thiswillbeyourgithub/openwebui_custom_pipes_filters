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
            default="^``` ?thinking", description="The start of thougt token."
        start_thought: str = Field(
        )
        end_thought: str = Field(
            default="```", description="The end of thought token."
        )

    def __init__(self):
        self.valves = self.Valves()
        self.p("Init:start")

        self.start_thought = re.compile(self.valves.start_thought)
        self.end_thought = re.compile(self.valves.end_thought)

        self.pattern = re.compile(
            rf"{self.valves.start_thought}(.*?){self.valves.end_thought}",
            flags=re.DOTALL | re.MULTILINE,
        )
        self.converted_pattern = re.compile(r"<details>\s*<summary>Reasonning</summary>.*?</details>", flags=re.DOTALL | re.MULTILINE)
        self.p("Init:done")
        pass

    def remove_thought(self, text: str) -> str:
        "remove thoughts"
        self.p("remove_thought: start")
        if not (self.pattern.search(text) or self.converted_pattern.search(text)):
            self.p("remove_thought: No thought to remove in text")
            return text
        assert text.strip(), "Received empty text"
        step1 = self.pattern.sub("", text)
        assert step1, "Empty text after step 1 of thought removal"
        step2 = self.converted_pattern.sub("", text)
        assert step2, "Empty text after step 2 of thought removal"
        self.p("remove_thought: done")
        return step2

    def hide_thought(self, text: str) -> str:
        "put the thoughts in <details> tags"
        self.p("hide_thought: start")
        match = self.pattern.search(text)
        if not match:
            self.p("hide_thought: No thought to hide in text")
            return text
        section = match.group()
        section = self.start_thought.sub("<details>\n<summary>Reasonning</summary>\n\n", section)
        section = self.stop_thought.sub("\n\n</details>\n", section)
        newtext = text.replace(match.group(), section)
        self.p("hide_thought: done")
        return newtext

    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        "reduce token count by removing thoughts in the previous messages"
        self.p("inlet:start")
        modified = 0
        for im, m in enumerate(body["messages"]):
            if "content" in m:
                if isinstance(m["content"], list):
                    for im2, m2 in enumerate(m["content"]):
                        if "content" in m2:
                            new = self.remove_thought(m2["content"])
                            if new != m2["content"]:
                                modified += 1
                            body["messages"][im]["content"][im2]["content"] = new
                        elif "text" in m2:
                            new = self.remove_thought(m2["text"])
                            if new != m2["text"]:
                                modified += 1
                            body["messages"][im]["content"][im2]["text"] = new
                else:
                    new = self.remove_thought(m["content"])
                    if new != m["content"]:
                        modified += 1
                    body["messages"][im]["content"] = new
        self.p(f"inlet:done: modified {modified} messages")
        return body

    async def outlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
    ) -> dict:
        self.p(f"outlet:{__user__}")
        # self.p(f"outlet:content:{body['messages'][-1]['content']}")
        # self.p(f"outlet:user:{__user__}")
        # self.p(str(body)

        assert isinstance(body, dict), f"Unexpected type of body: '{body}'"
        assert "messages" in body, f"Body is missing messages: '{body}'"
        last_message = body["messages"][-1]
        assert "content" in last_message, f"last_message does not have a 'content' key: '{last_message}'"
        last_message = last_message["content"]

        modified = 0

        if isinstance(last_message, list):
            for im2, m2 in enumerate(last_message):
                if "content" in m2:
                    new = self.hide_thought(m2["content"])
                    if new != m2["content"]:
                        modified += 1
                    body["messages"][-1]["content"][im2]["content"] = new
                elif "text" in m2:
                    new = self.hide_thought(m2["text"])
                    if new != m2["text"]:
                        modified += 1
                    body["messages"][-1]["content"][im2]["text"] = new

        elif isinstance(last_message, str):
            old = last_message.strip()
            new = self.hide_thought(old).strip()
            if old != new:
                modified += 1
                body["messages"][-1]["content"] = new
        else:
            raise Exception(f"outlet: Unexpected type of last_message: {type(last_message)}")

        self.p(f"outlet:done: modified {modified} messages")
        return body

    def p(self, message: str) -> None:
        "log message to logs"
        if self.valves.verbose:
            print("ThinkingFilter:outlet:" + message)
