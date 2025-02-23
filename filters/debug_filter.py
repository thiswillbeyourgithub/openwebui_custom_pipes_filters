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

import json
from pydantic import BaseModel, Field
from typing import Optional, Callable, Any

def p(message: str) -> None:
    print(f"DebugFilter: {message}")

class Filter:
    class Valves(BaseModel):
        priority: int = Field(
            default=0,
            description="Priority level for the filter operations (default 0).",
        )
        print_body: bool = Field(
            default=False,
            description="Print the body content",
        )
        print_user: bool = Field(
            default=False,
            description="Print the user info",
        )
        print_meta bool = Field(
            default=False,
            description="Print the metadata",
        )
        print_model: bool = Field(
            default=False,
            description="Print the model info",
        )
        print_files: bool = Field(
            default=False,
            description="Print the files info",
        )
        print_emitter: bool = Field(
            default=False,
            description="Print the event emitter",
        )

    def __init__(self):
        self.valves = self.Valves()

    async def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __metadata__: Optional[dict] = None,
        __model__: Optional[dict] = None,
        __files__: Optional[list] = None,
        __event_emitter__: Callable[[dict], Any] = None,
        ) -> dict:
        prio = self.valves.priority
        args_to_print = {
            "body": self.valves.print_body,
            "__user__": self.valves.print_user,
            "__metadata__": self.valves.print_metadata,
            "__model__": self.valves.print_model,
            "__files__": self.valves.print_files,
            "__event_emitter__": self.valves.print_emitter,
        }
        
        for arg, should_print in args_to_print.items():
            if should_print:
                try:
                    val = json.dumps(locals()[arg], ensure_ascii=False, indent=2)
                except:
                    val = str(locals()[arg])
                p(f"\nINLET_{prio}: {arg}:\n{val}")
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
        prio = self.valves.priority
        args_to_print = {
            "body": self.valves.print_body,
            "__user__": self.valves.print_user,
            "__metadata__": self.valves.print_metadata,
            "__model__": self.valves.print_model,
            "__files__": self.valves.print_files,
            "__event_emitter__": self.valves.print_emitter,
        }
        
        for arg, should_print in args_to_print.items():
            if should_print:
                try:
                    val = json.dumps(locals()[arg], ensure_ascii=False, indent=2)
                except:
                    val = str(locals()[arg])
                p(f"\nOUTLET_{prio}: {arg}:\n{val}")
        return body
