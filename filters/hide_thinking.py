"""
title: Thinking Filter
author: TrolleK
author_url: https://github.com/hosteren & https://huggingface.co/trollek
version: 0.3
"""

import re
from pydantic import BaseModel, Field
from typing import Optional, Callable, Any, Awaitable


class Filter:
    class UserValves(BaseModel):
        enable: bool = Field(default=True, description="True to remove thinking blocks")

    class Valves(BaseModel):
        start_thought_token: str = Field(
            default="^``` ?thinking", description="The start of thougt token."
        )
        end_thought_token: str = Field(
            default="```", description="The end of thought token."
        )

    def __init__(self):
        # Indicates custom file handling logic. This flag helps disengage default routines in favor of custom
        # implementations, informing the WebUI to defer file-related operations to designated methods within this class.
        # Alternatively, you can remove the files directly from the body in from the inlet hook
        # self.file_handler = True

        # Initialize 'valves' with specific configurations. Using 'Valves' instance helps encapsulate settings,
        # which ensures settings are managed cohesively and not confused with operational flags like 'file_handler'.
        self.valves = self.Valves()

        self.start_thought = re.compile(self.valves.start_thought_token)
        self.end_thought = re.compile(self.valves.end_thought_token)

        self.pattern = re.compile(
            rf"{self.valves.start_thought_token}(.*?){self.valves.end_thought_token}",
            flags=re.DOTALL | re.MULTILINE,
        )
        self.converted_pattern = re.compile(r"<details>\s*<summary>Reasonning</summary>.*?</details>")
        pass

    def remove_thought(self, text: str) -> str:
        "remove thoughts"
        if not (self.pattern.search(text) or self.converted_pattern.search(text)):
            return text
        assert text.strip(), "Received empty text"
        step1 = self.pattern.sub("", text).strip()
        assert step1, "Empty text after step 1 of thought removal"
        step2 = self.converted_pattern.sub("", text).strip()
        assert step2, "Empty text after step 2 of thought removal"
        return step2

    def hide_thought(self, text: str) -> str:
        "put the thoughts in <details> tags"
        match = self.pattern.search(text)
        if not match:
            return text
        section = match.group()
        section = self.start_thought.sub("<details>\n<summary>Reasonning</summary>\n\n", section)
        section = self.stop_thought.sub("\n\n</details>", section)
        newtext = text.replace(match.group(), section)
        return newtext

    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        "reduce token count by removing thoughts in the previous messages"
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
        return body

    def p(self, message: str) -> None:
        "log message to logs"
        print("ThinkingFilter:outlet:" + message)

    async def outlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
    ) -> dict:
        # Modify or analyze the response body after processing by the API.
        # This function is the post-processor for the API, which can be used to modify the response
        # or perform additional checks and analytics.
        self.p(f"outlet:{__user__}")
        # print(f"outlet:content:{body['messages'][-1]['content']}")
        # print(f"outlet:user:{__user__}")
        if not __user__["valves"].enable:
            self.p("outlet:disabled")
            return body
        # self.p(str(body)

        last_message = body["messages"][-1]["content"]
        if self.pattern.search(last_message):
            old = last_message.strip()
            new = self.remove_thought(old).strip()
            if old != new:
                self.p("outlet:Removed some thinking")
                body["messages"][-1]["content"] = new
            else:
                self.p("outlet:Unmodified text")
            if (not new) and old:
                body["messages"][-1]["content"] = old
                self.p("outlet:Empty after filtering, returning the whole thing")
        else:
            self.p("outlet: No thinking block found")
        return body


