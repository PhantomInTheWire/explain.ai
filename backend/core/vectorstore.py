import asyncio
from typing import Optional

import weaviate
from weaviate.classes.config import Configure, Property, DataType
from weaviate.classes.query import MetadataQuery
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from core.config import settings
from core.logging import get_logger

log = get_logger(__name__)


class VectorStoreManager:
    def __init__(self, weaviate_client: Optional[weaviate.WeaviateAsyncClient] = None):
        self._client: Optional[weaviate.WeaviateAsyncClient] = weaviate_client
        self._embeddings: Optional[GoogleGenerativeAIEmbeddings] = None
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return

        if self._client is None:
            host = (
                settings.weaviate_url.replace("http://", "")
                .replace("https://", "")
                .split(":")[0]
            )
            port = (
                int(settings.weaviate_url.split(":")[-1])
                if ":" in settings.weaviate_url.split("/")[-1]
                else 8080
            )
            # Use native async Weaviate client
            self._client = weaviate.use_async_with_custom(
                http_host=host,
                http_port=port,
                http_secure=settings.weaviate_url.startswith("https"),
                grpc_host=host,
                grpc_port=50051,
                grpc_secure=settings.weaviate_url.startswith("https"),
            )
            await self._client.connect()

        self._embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
        self._initialized = True
        log.info("vectorstore initialized with async client")

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._initialized = False

    @property
    def client(self) -> weaviate.WeaviateAsyncClient:
        if not self._initialized or self._client is None:
            raise RuntimeError("Vector store not initialized")
        return self._client

    @property
    def embeddings(self) -> GoogleGenerativeAIEmbeddings:
        if self._embeddings is None:
            raise RuntimeError("Vector store not initialized")
        return self._embeddings

    def _class_name(self, session_id: str) -> str:
        return f"Session_{session_id.replace('-', '_')}"

    async def create_session_collection(self, session_id: str) -> None:
        class_name = self._class_name(session_id)
        if await self.client.collections.exists(class_name):
            return

        await self.client.collections.create(
            name=class_name,
            vectorizer_config=Configure.Vectorizer.none(),
            properties=[
                Property(name="content", data_type=DataType.TEXT),
                Property(name="chunk_index", data_type=DataType.INT),
                Property(name="source_file", data_type=DataType.TEXT),
            ],
        )
        log.info("collection created", class_name=class_name)

    async def delete_session_collection(self, session_id: str) -> bool:
        class_name = self._class_name(session_id)
        if not await self.client.collections.exists(class_name):
            return False
        await self.client.collections.delete(class_name)
        log.info("collection deleted", class_name=class_name)
        return True

    async def add_documents(
        self, session_id: str, chunks: list[str], source_file: str = "uploaded.pdf"
    ) -> int:
        await self.create_session_collection(session_id)
        collection = self.client.collections.get(self._class_name(session_id))

        # Embeddings are still sync, wrap in asyncio.to_thread
        # TODO: Check if GoogleGenerativeAIEmbeddings has async methods in future LangChain versions
        vectors = await asyncio.to_thread(self._embeddings.embed_documents, chunks)

        # Use data.insert_many for async collections instead of batch
        objects = [
            {
                "properties": {
                    "content": chunk,
                    "chunk_index": i,
                    "source_file": source_file,
                },
                "vector": vector,
            }
            for i, (chunk, vector) in enumerate(zip(chunks, vectors))
        ]

        await collection.data.insert_many(objects)

        log.info("documents added", session_id=session_id, count=len(chunks))
        return len(chunks)

    async def similarity_search(
        self, session_id: str, query: str, k: int = 4
    ) -> list[dict]:
        class_name = self._class_name(session_id)
        if not await self.client.collections.exists(class_name):
            return []

        collection = self.client.collections.get(class_name)

        # Embeddings are still sync, wrap in asyncio.to_thread
        query_vector = await asyncio.to_thread(self._embeddings.embed_query, query)

        results = await collection.query.near_vector(
            near_vector=query_vector,
            limit=k,
            return_metadata=MetadataQuery(distance=True),
        )

        return [
            {
                "content": obj.properties.get("content", ""),
                "chunk_index": obj.properties.get("chunk_index", 0),
                "source_file": obj.properties.get("source_file", ""),
                "distance": obj.metadata.distance if obj.metadata else None,
            }
            for obj in results.objects
        ]

    async def get_all_documents(self, session_id: str) -> list[dict]:
        class_name = self._class_name(session_id)
        if not await self.client.collections.exists(class_name):
            return []

        collection = self.client.collections.get(class_name)
        docs = [
            {
                "content": obj.properties.get("content", ""),
                "chunk_index": obj.properties.get("chunk_index", 0),
                "source_file": obj.properties.get("source_file", ""),
            }
            async for obj in collection.iterator()
        ]
        docs.sort(key=lambda x: x["chunk_index"])
        return docs

    async def collection_exists(self, session_id: str) -> bool:
        return await self.client.collections.exists(self._class_name(session_id))

    async def list_collections(self) -> list[str]:
        collections = await self.client.collections.list_all()
        return [
            name.replace("Session_", "").replace("_", "-")
            for name in collections
            if name.startswith("Session_")
        ]


vectorstore_manager = VectorStoreManager()
