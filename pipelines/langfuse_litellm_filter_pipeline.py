"""
title: Langfuse Litellm Filter Pipeline
author: open-webui
date: 2025-03-28
version: 2.1
license: MIT
description: A filter pipeline that uses Langfuse and litellm.
original_source: https://github.com/open-webui/pipelines/pull/438
requirements: langfuse, loguru
"""


from typing import List, Optional
import os
import uuid
import json
import requests
import functools
from loguru import logger

from utils.pipelines.main import get_last_assistant_message
from pydantic import BaseModel
from langfuse import Langfuse
from langfuse.api.resources.commons.errors.unauthorized_error import UnauthorizedError


def get_last_assistant_message_obj(messages: List[dict]) -> dict:
    """Retrieve the last assistant message from the message list."""
    for message in reversed(messages):
        if message["role"] == "assistant":
            return message
    return {}


class Pipeline:
    VERSION: str = [li for li in __doc__.splitlines() if li.startswith("version: ")][0].split("version: ")[1]

    class Valves(BaseModel):
        pipelines: List[str] = []
        priority: int = 0
        secret_key: str
        public_key: str
        host: str
        # New valve that controls whether task names are added as tags:
        insert_tags: bool = True
        # Controls which model identifier to use for generation
        modelkey_identifier_type: str = "id"  # can be "id", "name", or "litellm"
        debug: bool = False
        # LiteLLM configuration
        litellm_host: str = "localhost"
        litellm_port: str = "4000"
        litellm_api_key: str = ""

    def __init__(self):
        self.type = "filter"
        self.name = "Langfuse Litellm Filter"

        self.valves = self.Valves(
            **{
                "pipelines": ["*"],
                "secret_key": os.getenv("LANGFUSE_SECRET_KEY", "your-secret-key-here"),
                "public_key": os.getenv("LANGFUSE_PUBLIC_KEY", "your-public-key-here"),
                "host": os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
                "modelkey_identifier_type": os.getenv("modelkey_identifier_TYPE", "id"),
                "debug": os.getenv("DEBUG_MODE", "false").lower() == "true",
                "litellm_host": os.getenv("LITELLM_HOST", "localhost"),
                "litellm_port": os.getenv("LITELLM_PORT", "4000"),
                "litellm_api_key": os.getenv("LITELLM_API_KEY", ""),
            }
        )

        self.langfuse = None
        self.chat_traces = {}
        self.suppressed_logs = set()
        # Dictionary to store model names for each chat
        self.model_names = {}

        # Only these tasks will be treated as LLM "generations":
        self.GENERATION_TASKS = {"llm_response"}

    def log(self, message: str, suppress_repeats: bool = False):
        if self.valves.debug:
            if suppress_repeats:
                if message in self.suppressed_logs:
                    return
                self.suppressed_logs.add(message)
            logger.debug(message)

    async def on_startup(self):
        self.log(f"on_startup triggered for {__name__}")
        self.set_langfuse()

    async def on_shutdown(self):
        self.log(f"on_shutdown triggered for {__name__}")
        if self.langfuse:
            self.langfuse.flush()

    async def on_valves_updated(self):
        self.log("Valves updated, resetting Langfuse client.")
        # Validate modelkey_identifier_type
        valid_types = ["name", "id", "litellm"]
        if self.valves.modelkey_identifier_type not in valid_types:
            raise ValueError(f"Invalid modelkey_identifier_type: '{self.valves.modelkey_identifier_type}'. Must be one of: {', '.join(valid_types)}")
        self.set_langfuse()

    def set_langfuse(self):
        try:
            self.langfuse = Langfuse(
                secret_key=self.valves.secret_key,
                public_key=self.valves.public_key,
                host=self.valves.host,
                debug=self.valves.debug,
            )
            self.langfuse.auth_check()
            self.log("Langfuse client initialized successfully.")
        except UnauthorizedError:
            logger.error(
                "Langfuse credentials incorrect. Please re-enter your Langfuse credentials in the pipeline settings."
            )
        except Exception as e:
            logger.error(
                f"Langfuse error: {e} Please re-enter your Langfuse credentials in the pipeline settings."
            )

    def _build_tags(self, task_name: str) -> list:
        """
        Builds a list of tags based on valve settings, ensuring we always add
        'open-webui' and skip user_response / llm_response from becoming tags themselves.
        """
        tags_list = []
        if self.valves.insert_tags:
            # Always add 'open-webui'
            tags_list.append("open-webui")
            # Add the task_name if it's not one of the excluded defaults
            if task_name not in ["user_response", "llm_response"]:
                tags_list.append(task_name)
        return tags_list

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        if self.valves.debug:
            logger.debug(f"Received request: {json.dumps(body, indent=2)}")

        self.log(f"Inlet function called with body: {body} and user: {user}")

        metadata = body.get("metadata", {})
        chat_id = metadata.get("chat_id", str(uuid.uuid4()))
        metadata["chat_id"] = chat_id
        body["metadata"] = metadata

        # Extract and store both model name and ID if available
        model_info = metadata.get("model", {})
        model_id = body.get("model")

        # Store model information for this chat
        if chat_id not in self.model_names:
            self.model_names[chat_id] = {"id": model_id}
        else:
            self.model_names[chat_id]["id"] = model_id

        if isinstance(model_info, dict) and "name" in model_info:
            self.model_names[chat_id]["name"] = model_info["name"]
            self.log(f"Stored model info - name: '{model_info['name']}', id: '{model_id}' for chat_id: {chat_id}")

        required_keys = ["model", "messages"]
        missing_keys = [key for key in required_keys if key not in body]
        if missing_keys:
            error_message = f"Error: Missing keys in the request body: {', '.join(missing_keys)}"
            self.log(error_message)
            raise ValueError(error_message)

        user_email = user.get("email") if user else None
        # Defaulting to 'user_response' if no task is provided
        task_name = metadata.get("task", "user_response")

        # Build tags
        tags_list = self._build_tags(task_name)

        if chat_id not in self.chat_traces:
            self.log(f"Creating new trace for chat_id: {chat_id}")

            trace_payload = {
                "name": f"chat:{chat_id}",
                "input": body,
                "user_id": user_email,
                "metadata": metadata,
                "session_id": chat_id,
            }

            if tags_list:
                trace_payload["tags"] = tags_list

            if self.valves.debug:
                logger.debug(f"Langfuse trace request: {json.dumps(trace_payload, indent=2)}")

            trace = self.langfuse.trace(**trace_payload)
            self.chat_traces[chat_id] = trace
        else:
            trace = self.chat_traces[chat_id]
            self.log(f"Reusing existing trace for chat_id: {chat_id}")
            if tags_list:
                trace.update(tags=tags_list)

        # Update metadata with type
        metadata["type"] = task_name
        metadata["interface"] = "open-webui"

        # If it's a task that is considered an LLM generation
        if task_name in self.GENERATION_TASKS:
            # Determine which model value to use based on the use_model_name valve
            model_id = self.model_names.get(chat_id, {}).get("id", body["model"])
            model_name = self.model_names.get(chat_id, {}).get("name", "unknown")

            # Pick primary model identifier based on valve setting
            if self.valves.modelkey_identifier_type == "name":
                model_value = model_name
            elif self.valves.modelkey_identifier_type == "litellm":
                try:
                    model_value = self.get_actual_model_name(model_id)
                except Exception as e:
                    self.log(f"Error retrieving actual model name: {str(e)}. Falling back to model ID.")
                    model_value = model_id
            elif self.valves.modelkey_identifier_type == "id":
                model_value = model_id
            else:
                # This should never happen due to validation in on_valves_updated
                raise ValueError(f"Invalid modelkey_identifier_type: '{self.valves.modelkey_identifier_type}'")

            # Add both values to metadata regardless of valve setting
            metadata[f"openwebui_{task_name}_model_id"] = model_id
            metadata[f"openwebui_{task_name}_model_name"] = model_name

            generation_payload = {
                "name": f"{task_name}:{str(uuid.uuid4())}",
                "model": model_value,
                "input": body["messages"],
                "metadata": metadata,
            }
            if tags_list:
                generation_payload["tags"] = tags_list

            if self.valves.debug:
                logger.debug(f"Langfuse generation request: {json.dumps(generation_payload, indent=2)}")

            trace.generation(**generation_payload)
        else:
            # Otherwise, log it as an event
            event_payload = {
                "name": f"{task_name}:{str(uuid.uuid4())}",
                "metadata": metadata,
                "input": body["messages"],
            }
            if tags_list:
                event_payload["tags"] = tags_list

            if self.valves.debug:
                logger.debug(f"Langfuse event request: {json.dumps(event_payload, indent=2)}")

            trace.event(**event_payload)

        return body

    @functools.lru_cache(maxsize=128)
    def get_actual_model_name(self, model_alias: str) -> str:
        """
        Retrieves the actual model name from LiteLLM API based on the provided model alias.
        Results are cached using functools.lru_cache to improve performance.

        Args:
            model_alias (str): The alias of the model (e.g., "litellm_sonnet-3.7")

        Returns:
            str: The actual model name (e.g., "openrouter/anthropic/claude-3.7-sonnet:thinking")

        Raises:
            ValueError: If required environment variables are missing
            ConnectionError: If connection to LiteLLM API fails
            KeyError: If the model is not found in the API response
            Exception: For other unexpected errors
        """
        # Get LiteLLM configuration from valves
        host = self.valves.litellm_host
        port = self.valves.litellm_port
        api_key = self.valves.litellm_api_key

        if not api_key:
            raise ValueError("LiteLLM API key must be set either in the pipeline valve or as LITELLM_API_KEY environment variable")

        try:
            # Construct the API URL
            url = f"http://{host}:{port}/model/info"

            # Set up headers
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }

            # Make the API request
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # Raise exception for HTTP errors

            # Parse the response
            data = response.json().get("data", [])

            # Find the model in the response
            for model_info in data:
                if model_info.get("model_name") == model_alias:
                    actual_model = model_info.get("litellm_params", {}).get("model")
                    logger.info(f"LiteLLM model mapping: '{model_alias}' → '{actual_model}'")
                    return actual_model

            raise KeyError(f"Model '{model_alias}' not found in LiteLLM API response")

        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Failed to connect to LiteLLM API: {str(e)}")
        except json.JSONDecodeError:
            raise Exception("Failed to parse LiteLLM API response")
        except Exception as e:
            raise Exception(f"Error retrieving model information: {str(e)}")

    async def outlet(self, body: dict, user: Optional[dict] = None) -> dict:
        self.log(f"Outlet function called with body: {body}")

        chat_id = body.get("chat_id")
        metadata = body.get("metadata", {})
        # Defaulting to 'llm_response' if no task is provided
        task_name = metadata.get("task", "llm_response")

        # Build tags
        tags_list = self._build_tags(task_name)

        if chat_id not in self.chat_traces:
            self.log(f"[WARNING] No matching trace found for chat_id: {chat_id}, attempting to re-register.")
            # Re-run inlet to register if somehow missing
            return await self.inlet(body, user)

        trace = self.chat_traces[chat_id]

        assistant_message = get_last_assistant_message(body["messages"])
        assistant_message_obj = get_last_assistant_message_obj(body["messages"])

        usage = None
        if assistant_message_obj:
            info = assistant_message_obj.get("usage", {})
            if isinstance(info, dict):
                input_tokens = info.get("prompt_eval_count") or info.get("prompt_tokens")
                output_tokens = info.get("eval_count") or info.get("completion_tokens")
                if input_tokens is not None and output_tokens is not None:
                    usage = {
                        "input": input_tokens,
                        "output": output_tokens,
                        "unit": "TOKENS",
                    }
                    self.log(f"Usage data extracted: {usage}")

        # Update the trace output with the last assistant message
        trace.update(output=assistant_message)

        metadata["type"] = task_name
        metadata["interface"] = "open-webui"

        if task_name in self.GENERATION_TASKS:
            # Determine which model value to use based on the use_model_name valve
            model_id = self.model_names.get(chat_id, {}).get("id", body.get("model"))
            model_name = self.model_names.get(chat_id, {}).get("name", "unknown")

            # Pick primary model identifier based on valve setting
            if self.valves.modelkey_identifier_type == "name":
                model_value = model_name
            elif self.valves.modelkey_identifier_type == "litellm":
                try:
                    model_value = self.get_actual_model_name(model_id)
                except Exception as e:
                    self.log(f"Error retrieving actual model name: {str(e)}. Falling back to model ID.")
                    model_value = model_id
            elif self.valves.modelkey_identifier_type == "id":
                model_value = model_id
            else:
                # This should never happen due to validation in on_valves_updated
                raise ValueError(f"Invalid modelkey_identifier_type: '{self.valves.modelkey_identifier_type}'")

            # Add both values to metadata regardless of valve setting
            metadata[f"openwebui_{task_name}_model_id"] = model_id
            metadata[f"openwebui_{task_name}_model_name"] = model_name

            # If it's an LLM generation
            generation_payload = {
                "name": f"{task_name}:{str(uuid.uuid4())}",
                "model": model_value,   # <-- Use model name or ID based on valve setting
                "input": body["messages"],
                "metadata": metadata,
                "usage": usage,
            }
            if tags_list:
                generation_payload["tags"] = tags_list

            if self.valves.debug:
                logger.debug(f"Langfuse generation end request: {json.dumps(generation_payload, indent=2)}")

            trace.generation().end(**generation_payload)
            self.log(f"Generation ended for chat_id: {chat_id}")
        else:
            # Otherwise log as an event
            event_payload = {
                "name": f"{task_name}:{str(uuid.uuid4())}",
                "metadata": metadata,
                "input": body["messages"],
            }
            if usage:
                # If you want usage on event as well
                event_payload["metadata"]["usage"] = usage

            if tags_list:
                event_payload["tags"] = tags_list

            if self.valves.debug:
                logger.debug(f"Langfuse event end request: {json.dumps(event_payload, indent=2)}")

            trace.event(**event_payload)
            self.log(f"Event logged for chat_id: {chat_id}")

        return body
