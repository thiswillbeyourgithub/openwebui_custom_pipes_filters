"""
title: Thinking Filter
author: TrolleK
author_url: https://github.com/hosteren & https://huggingface.co/trollek
version: 0.1
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
        self.uvalves = self.UserValves()
        self.valves = self.Valves()

        self.pattern = re.compile(
            rf"{self.valves.start_thought_token}(.*?){self.valves.end_thought_token}",
            flags=re.DOTALL | re.MULTILINE,
        )
        pass

    def remove_thought(self, text: str) -> str:
        # Remove thought markers from text and return the modified text.
        # This function is used to remove thought markers from a string of text, which are typically used in chat applications to indicate that a message contains a thought or an idea.
        return self.pattern.sub("", text)

    # def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
    # Modify the request body or validate it before processing by the chat completion API.
    # This function is the pre-processor for the API where various checks on the input can be performed.
    # It can also modify the request before sending it to the API.
    # print(f"inlet:{__name__}")
    # print(f"inlet:body:{body}")
    # print(f"inlet:user:{__user__}")
    # return body

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
        if not self.uvalves.enable:
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

