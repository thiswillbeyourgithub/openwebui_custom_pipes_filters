"""
title: WDoc Pipeline
author: thiswillbeyourgithub
date: 2024-09-02
version: 1.0
license: MIT
description: A pipeline to use RAG direcctly in open-webui
requirements: WDoc
"""

from typing import List, Union, Generator, Iterator
from schemas import OpenAIChatMessage
import os

from pydantic import BaseModel


class Pipeline:

    class Valves(BaseModel):
        LLAMAINDEX_OLLAMA_BASE_URL: str
        LLAMAINDEX_MODEL_NAME: str
        LLAMAINDEX_EMBEDDING_MODEL_NAME: str

    def __init__(self):
        self.documents = None
        self.index = None

        self.valves = self.Valves(
            **{
                "LLAMAINDEX_OLLAMA_BASE_URL": os.getenv("LLAMAINDEX_OLLAMA_BASE_URL", "http://localhost:11434"),
                "LLAMAINDEX_MODEL_NAME": os.getenv("LLAMAINDEX_MODEL_NAME", "llama3"),
                "LLAMAINDEX_EMBEDDING_MODEL_NAME": os.getenv("LLAMAINDEX_EMBEDDING_MODEL_NAME", "nomic-embed-text"),
            }
        )

    async def on_startup(self):
        print("Importing WDoc")
        try:
            from WDoc import WDoc
        except Exception as err:
            raise Exception(f"Failed to import WDoc: '{err}'")
        try:
            self.wdoc = WDoc(
                task="query",
                import_mode=True,
                query="this is a test",
            )
        except Exception as err:
            raise Exception(f"Failed to create WDoc instance: '{err}'")
        print("Succesfully create wdoc instance!")

        # from llama_index.embeddings.ollama import OllamaEmbedding
        # from llama_index.llms.ollama import Ollama
        # from llama_index.core import Settings, VectorStoreIndex, SimpleDirectoryReader
        #
        # Settings.embed_model = OllamaEmbedding(
        #     model_name=self.valves.LLAMAINDEX_EMBEDDING_MODEL_NAME,
        #     base_url=self.valves.LLAMAINDEX_OLLAMA_BASE_URL,
        # )
        # Settings.llm = Ollama(
        #     model=self.valves.LLAMAINDEX_MODEL_NAME,
        #     base_url=self.valves.LLAMAINDEX_OLLAMA_BASE_URL,
        # )
        #
        # # This function is called when the server is started.
        # global documents, index
        #
        # self.documents = SimpleDirectoryReader("/app/backend/data").load_data()
        # self.index = VectorStoreIndex.from_documents(self.documents)
        pass

    async def on_shutdown(self):
        # This function is called when the server is stopped.
        pass

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        # This is where you can add your custom RAG pipeline.
        # Typically, you would retrieve relevant information from your knowledge base and synthesize it to generate a response.

        print(messages)
        print(user_message)

        raise NotImplementedError("WDoc is not yet available")

        # query_engine = self.index.as_query_engine(streaming=True)
        # response = query_engine.query(user_message)
        #
        # return response.response_gen
