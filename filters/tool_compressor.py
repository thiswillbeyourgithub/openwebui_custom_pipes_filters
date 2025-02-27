"""
title: tool_compressor
author: thiswillbeyourightub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
git_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters
version: 1.0.0
date: 2025-02-21
license: GPLv3
description: A Filter that makes more compact the tool calls (turn the <details> escaped html (token expensive!) into regular unescaped html, or even removed.
openwebui_url: https://openwebui.com/f/qqqqqqqqqqqqqqqqqqqq/tool_compressor
"""

from pydantic import BaseModel, Field
from typing import Optional, Callable, Any
import html
import re


class Filter:
    class Valves(BaseModel):
        priority: int = Field(
            default=0,
            description="Priority level for the filter operations (default 0).",
        )
        debug: bool = Field(
            default=True,
            description="Use debug prints",
        )
        remove_results: bool = Field(
            default=True,
            description="Delete the results field",
        )
        remove_content: bool = Field(
            default=True,
            description="Delete the content field",
        )

    def __init__(self):
        self.valves = self.Valves()

    def log(self, message: str):
        if self.valves.debug:
            print(f"ToolCompressor: {message}")

    def compress_tool_calls(self, text: str) -> str:
        orig_text = text
        details = re.findall(r'<details type="tool_calls" done="true" .*?</details>', text, flags=re.DOTALL|re.MULTILINE)
        if not details:
            self.log("No tool_calls in message")
            return text

        if len(details) > 1:
            compressed_details = [self.compress_tool_calls(text=detail) for detail in details]
            n = len(details)
            for idet, (comp, det) in enumerate(zip(compressed_details, details)):
                assert det in text, f"Couldn't find detail tag #{i}/{n}: '{det}'"
                text = text.replace(det, comp)
            return text

        match = re.search(r'details type="tool_calls" done="true" content="([^"]*?)" results="([^"]*)"', text, flags=re.DOTALL|re.MULTILINE)
        assert match, f"Couldn't match tool call '{text}'"

        content2 = html.unescape(match.group(1))
        results2 = html.unescape(match.group(2))
        
        # Replace the original content with the new format
        text = text.replace(f' content="{match.group(1)}"', "")
        text = text.replace(f' results="{match.group(2)}"', "")

        text = text.replace("</details>", "\n")

        if not self.valves.remove_content:
            text += f"""Results: {content2}"""
        if not self.valves.remove_results:
            text += f"""Results: {results2}"""
        if not text.endswith("</details>"):
            text += "\n</details>"
        return text

    async def inlet(
        self,
        body: dict,
        ) -> dict:
        self.log("Inlet")
        for im, m in enumerate(body["messages"]):
            body["messages"][im]["content"] = self.compress_tool_calls(m["content"])
        return body

    def outlet(
        self,
        body: dict,
        ) -> dict:
        self.log("Outlet")
        for im, m in enumerate(body["messages"]):
            body["messages"][im]["content"] = self.compress_tool_calls(m["content"])
        return body
