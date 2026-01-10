"""
title: debug_filter
author: thiswillbeyourightub
author_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
funding_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters/
git_url: https://github.com/thiswillbeyourgithub/openwebui_custom_pipes_filters
version: 2.6.0
date: 2025-05-09
license: AGPLv3
description: Filter that prints argument as they pass through it. You can use it multiple times to debug another filter. You can then use `docker logs open-webui --tail 100 --follow | grep DebugFilter` to see the data that interests you.
openwebui_url: https://openwebui.com/f/qqqqqqqqqqqqqqqqqqqq/debug_filter
"""

import json
from pydantic import BaseModel, Field
from typing import Optional, Callable, Any, Literal, List, Dict
from loguru import logger
from open_webui.models.tools import ToolUserModel


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
            default=True,
            description="Print the body content",
        )
        print_user: bool = Field(
            default=True,
            description="Print the user info",
        )
        print_metadata: bool = Field(
            default=True,
            description="Print the metadata",
        )
        print_model: bool = Field(
            default=True,
            description="Print the model info",
        )
        print_files: bool = Field(
            default=True,
            description="Print the files info",
        )
        print_emitter: bool = Field(
            default=True,
            description="Print the event emitter",
        )
        print_messages: bool = Field(
            default=True,
            description="Print the messages list",
        )
        print_chat_id: bool = Field(
            default=True,
            description="Print the chat ID",
        )
        print_session_id: bool = Field(
            default=True,
            description="Print the session ID",
        )
        print_message_id: bool = Field(
            default=True,
            description="Print the message ID",
        )
        print_request: bool = Field(
            default=True,
            description="Print the request object (converted to string)",
        )
        print_task: bool = Field(
            default=True,
            description="Print the task info",
        )
        print_task_body: bool = Field(
            default=True,
            description="Print the task_body info",
        )
        print_tools: bool = Field(
            default=True,
            description="Print the tools info",
        )
        direction: Literal["inlet", "outlet", "both"] = Field(
            default="both",
            description="When to print debug info: 'inlet', 'outlet', or 'both'",
        )
        compress_output: bool = Field(
            default=True,
            description="When true, JSON output is compact (single line). When false, it's indented and readable.",
        )

    def __init__(self):
        self.valves = self.Valves()

    async def inlet(
        self,
        body: Dict,
        __user__: Dict = None,
        __metadata__: Dict = None,
        __model__: Dict = None,
        __messages__: List = None,
        __chat_id__: str = None,
        __message_id__: str = None,
        __request__: Any = None,
        __session_id__: str = None,
        __files__: Optional[list] = None,
        __event_emitter__: Callable[[Dict], Any] = None,
        __task__: Optional[str] = None,
        __task_body__: Optional[Dict] = None,
        __tools__: Optional[List[ToolUserModel]] = None,
    ) -> Dict:
        if self.valves.direction == "outlet":
            return body
        prio = self.valves.priority
        args_to_print = {
            "body": self.valves.print_body,
            "__user__": self.valves.print_user,
            "__metadata__": self.valves.print_metadata,
            "__model__": self.valves.print_model,
            "__files__": self.valves.print_files,
            "__event_emitter__": self.valves.print_emitter,
            "__messages__": self.valves.print_messages,
            "__chat_id__": self.valves.print_chat_id,
            "__session_id__": self.valves.print_session_id,
            "__message_id__": self.valves.print_message_id,
            "__request__": self.valves.print_request,
            "__task__": self.valves.print_task,
            "__task_body__": self.valves.print_task_body,
            "__tools__": self.valves.print_tools,
        }
        for arg, should_print in args_to_print.items():
            if should_print:
                try:
                    try:
                        indent = None if self.valves.compress_output else 2
                        val = json.dumps(
                            locals()[arg], ensure_ascii=False, indent=indent
                        )
                    except Exception:
                        val = str(locals()[arg])
                    val_lines = val.strip().splitlines()
                    for vl in val_lines:
                        p(f"INLET_{prio}: {arg}: {vl}")
                except Exception as ee:
                    p(f"INLET_{prio}: {arg}: Exception when printing value: '{ee}'")
        return body

    def outlet(
        self,
        body: Dict,
        __user__: Dict = None,
        __metadata__: Dict = None,
        __model__: Dict = None,
        __messages__: List = None,
        __chat_id__: str = None,
        __session_id__: str = None,
        __message_id__: str = None,
        __request__: Any = None,
        __files__: Optional[list] = None,
        __event_emitter__: Callable[[Dict], Any] = None,
        __task__: Optional[str] = None,
        __task_body__: Optional[Dict] = None,
        __tools__: Optional[List[ToolUserModel]] = None,
    ) -> Dict:
        if self.valves.direction == "inlet":
            return body
        prio = self.valves.priority
        args_to_print = {
            "body": self.valves.print_body,
            "__user__": self.valves.print_user,
            "__metadata__": self.valves.print_metadata,
            "__model__": self.valves.print_model,
            "__files__": self.valves.print_files,
            "__event_emitter__": self.valves.print_emitter,
            "__messages__": self.valves.print_messages,
            "__chat_id__": self.valves.print_chat_id,
            "__session_id__": self.valves.print_session_id,
            "__message_id__": self.valves.print_message_id,
            "__request__": self.valves.print_request,
            "__task__": self.valves.print_task,
            "__task_body__": self.valves.print_task_body,
            "__tools__": self.valves.print_tools,
        }
        for arg, should_print in args_to_print.items():
            if should_print:
                try:
                    try:
                        indent = None if self.valves.compress_output else 2
                        val = json.dumps(
                            locals()[arg], ensure_ascii=False, indent=indent
                        )
                    except Exception:
                        val = str(locals()[arg])
                    val_lines = val.strip().splitlines()
                    for vl in val_lines:
                        p(f"OUTLET_{prio}: {arg}: {vl}")
                except Exception as ee:
                    p(f"OUTLET_{prio}: {arg}: Exception when printing value: '{ee}'")
        return body
