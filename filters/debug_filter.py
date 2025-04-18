"""
title: debug_filter
author: thiswillbeyourightub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
git_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters
version: 2.3.0
date: 2025-03-23
license: GPLv3
description: Filter that prints argument as they pass through it. You can use it multiple times to debug another filter.
openwebui_url: https://openwebui.com/f/qqqqqqqqqqqqqqqqqqqq/debug_filter
"""

import json
from pydantic import BaseModel, Field
from typing import Optional, Callable, Any
from loguru import logger


def p(message: str) -> None:
    logger.info(f"DebugFilter: {message}")


class Filter:
    VERSION: str = [li for li in __doc__.splitlines() if li.startswith("version: ")][
        0
    ].split("version: ")[1]

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
        print_metadata: bool = Field(
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
        direction: str = Field(
            default="both",
            description="When to print debug info: 'inlet', 'outlet', or 'both'",
        )
        compress_output: bool = Field(
            default=False,
            description="When true, JSON output is compact (single line). When false, it's indented and readable.",
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

        if self.valves.direction in ["inlet", "both"]:
            for arg, should_print in args_to_print.items():
                if should_print:
                    try:
                        indent = None if self.valves.compress_output else 2
                        val = json.dumps(
                            locals()[arg], ensure_ascii=False, indent=indent
                        )
                    except:
                        val = str(locals()[arg])
                    val_lines = val.strip().splitlines()
                    for vl in val_lines:
                        p(f"INLET_{prio}: {arg}: {vl}")
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

        if self.valves.direction in ["outlet", "both"]:
            for arg, should_print in args_to_print.items():
                if should_print:
                    try:
                        indent = None if self.valves.compress_output else 2
                        val = json.dumps(
                            locals()[arg], ensure_ascii=False, indent=indent
                        )
                    except:
                        val = str(locals()[arg])
                    val_lines = val.strip().splitlines()
                    for vl in val_lines:
                        p(f"OUTLET_{prio}: {arg}: {vl}")
        return body
