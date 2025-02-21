"""
title: debug_filter
author: thiswillbeyourightub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
git_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters
version: 1.0.0
date: 2025-02-21
license: GPLv3
description: A Filter that prints arguments as they go through it
openwebui_url: https://openwebui.com/f/qqqqqqqqqqqqqqqqqqqq/debug_filter
"""

from pydantic import BaseModel
from typing import Optional, Callable, Any

def p(message: str) -> None:
    print(f"DebugFilter: {message}")

class Filter:
    async def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __metadata__: Optional[dict] = None,
        __model__: Optional[dict] = None,
        __files__: Optional[list] = None,
        __event_emitter__: Callable[[dict], Any] = None,
        ) -> dict:
        for arg in ["body", "__user__", "__metadata__", "__model__", "__files__", "__event_emitter__"]:
            try:
                val = json.dumps(locals()["arg"], ensure_ascii=False, indent=2)
            except:
                val = str(locals()[arg])
            p(f"\nINLET: {arg}:\n{val}")
        return body

    def outlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __metadata__: Optional[dict] = None,
        __model__: Optional[dict] = None,
        __files__: Optional[list] = None,
        __event_emitter__: Callable[[dict], Any] = None,
        ) -> dict:
        for arg in ["body", "__user__", "__metadata__", "__model__", "__files__", "__event_emitter__"]:
            try:
                val = json.dumps(locals()["arg"], ensure_ascii=False, indent=2)
            except:
                val = str(locals()[arg])
            p(f"\nOUTLET: {arg}:\n{val}")
        return body
