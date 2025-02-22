"""
title: tool_compressor
author: thiswillbeyourightub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
git_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters
version: 1.0.0
date: 2025-02-21
license: GPLv3
description: A Filter that makes more compact the tool calls (turn the <details> escaped html into regular unescaped html.
openwebui_url: https://openwebui.com/f/qqqqqqqqqqqqqqqqqqqq/tool_compressor
"""

from pydantic import BaseModel, Field
from typing import Optional, Callable, Any
import html
import json
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

    def __init__(self):
        self.valves = self.Valves()

    def log(self, message: str):
        if self.valves.debug:
            print(f"ToolCompressor: {message}")

    def unescape_tool_calls(self, text: str) -> str:
        orig_text = text
        details = re.findall(r'(<details type="tool_calls" .*?>).*?(</details>)', text)
        if not details:
            self.log("No tool_calls in message")
            return text

        if len(details) > 1:
            compressed_details = [self.unescape_tool_calls(text=detail) for detail in details]
            n = len(details)
            for idet, comp, det in enumerate(zip(compressed_details, details)):
                assert det in text, f"Couldn't find detail tag #{i}/{n}: '{det}'"
                text = text.replace(det, comp)
            return text

        match = re.search(r'details type="tool_calls" done="true" content="([^"]*?)" results="([^"]*)"', text)
        assert match, f"Couldn't match tool call '{text}'"
        
        # Decode HTML entities and parse JSON
        content_u = html.unescape(match.group(1))
        content_l = json.loads(content_u)

        results_u = html.unescape(match.group(2))
        results_l = json.loads(results_u)
        
        # # Create the new format
        # new_content = json.dumps(data, indent=2)
        
        # Replace the original content with the new format
        text = text.replace(f' content="{match.group(1)}"', "")
        text = text.replace(f' results="{match.group(2)}"', "")
        text = text + f"""
Content: {content_l}

Results: {results_l}"""
        
        return textt

    async def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __metadata__: Optional[dict] = None,
        __model__: Optional[dict] = None,
        __files__: Optional[list] = None,
        __event_emitter__: Callable[[dict], Any] = None,
        ) -> dict:
        self.log("Inlet")
        for im, m in enumerate(body["messages"]):
            body["messages"][im]["content"] = self.unescape_tool_calls(m["content"])
        return body

    def outlet(
        self,
        body: dict,
        ) -> dict:
        self.log("Outlet")
        for im, m in enumerate(body["messages"]):
            body["messages"][im]["content"] = self.unescape_tool_calls(m["content"])
        return body


if __name__ == "__main__":
    s = """</details> <details type="tool_calls" done="true" content="[{&quot;id&quot;: &quot;tooluse_ztmZwehmSarRxaLMz6Q4Lw&quot;, &quot;function&quot;: {&quot;arguments&quot;: &quot;{\&quot;fields\&quot;: {\&quot;body\&quot;: \&quot;Quelle est la d\u00e9viation axiale dans l&#x27;h\u00e9mibloc ant\u00e9rieur gauche ?&lt;br&gt;{{c1::Un axe hypergauche}}&lt;br&gt;(Crit\u00e8re n\u00e9cessaire mais non suffisant)\&quot;, \&quot;source\&quot;: \&quot;https://www.e-cardiogram.com/bloc-fasciculaire-anterieur-gauche/ et https://www.e-cardiogram.com/bloc-fasciculaire-posterieur-gauche/\&quot;}}&quot;, &quot;name&quot;: &quot;create_flashcard&quot;}, &quot;type&quot;: &quot;function&quot;, &quot;index&quot;: 0}]" results="[{&quot;tool_call_id&quot;: &quot;tooluse_ztmZwehmSarRxaLMz6Q4Lw&quot;, &quot;content&quot;: &quot; body: Quelle est la d\u00e9viation axiale dans l&#x27;h\u00e9mibloc ant\u00e9rieur gauche ?&lt;br&gt;{{c1::Un axe hypergauche}}&lt;br&gt;(Crit\u00e8re n\u00e9cessaire mais non suffisant),\r source: https://www.e-cardiogram.com/bloc-fasciculaire-anterieur-gauche/ et https://www.e-cardiogram.com/bloc-fasciculaire-posterieur-gauche/,\r note_id: 1740150607167&quot;}]"> <summary>Tool Executed</summary>"""
    filt = Filter()
    print(filt.unescape_tool_calls(s))
