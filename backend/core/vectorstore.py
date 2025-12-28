import asyncio
from typing import Optional

import weaviate
from weaviate.classes.config import Configure, Property, DataType
from weaviate.classes.query import MetadataQuery
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from backend.core.config import settings
from backend.core.logging import get_logger

log = get_logger(__name__)


class VectorStoreManager:
    def __init__(self, weaviate_client: Optional[weaviate.WeaviateClient] = None):
        self._client: Optional[weaviate.WeaviateClient] = weaviate_client
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
            self._client = await asyncio.to_thread(
                weaviate.connect_to_custom,
                http_host=host,
                http_port=port,
                http_secure=settings.weaviate_url.startswith("https"),
                grpc_host=host,
                grpc_port=50051,
                grpc_secure=settings.weaviate_url.startswith("https"),
            )

        self._embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
        self._initialized = True
        log.info("vectorstore initialized")

    def _get_sync_client(self) -> weaviate.WeaviateClient:
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
            self._client = weaviate.connect_to_custom(
                http_host=host,
                http_port=port,
                http_secure=settings.weaviate_url.startswith("https"),
                grpc_host=host,
                grpc_port=50051,
                grpc_secure=settings.weaviate_url.startswith("https"),
            )
            self._embeddings = GoogleGenerativeAIEmbeddings(
                model="models/embedding-001"
            )
            self._initialized = True
        return self._client

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._initialized = False

    @property
    def client(self) -> weaviate.WeaviateClient:
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

    def _create_collection_sync(self, session_id: str) -> None:
        client = self._get_sync_client()
        class_name = self._class_name(session_id)
        if client.collections.exists(class_name):
            return

        client.collections.create(
            name=class_name,
            vectorizer_config=Configure.Vectorizer.none(),
            properties=[
                Property(name="content", data_type=DataType.TEXT),
                Property(name="chunk_index", data_type=DataType.INT),
                Property(name="source_file", data_type=DataType.TEXT),
            ],
        )
        log.info("collection created", class_name=class_name)

    async def create_session_collection(self, session_id: str) -> None:
        await asyncio.to_thread(self._create_collection_sync, session_id)

    def _delete_collection_sync(self, session_id: str) -> bool:
        client = self._get_sync_client()
        class_name = self._class_name(session_id)
        if not client.collections.exists(class_name):
            return False
        client.collections.delete(class_name)
        log.info("collection deleted", class_name=class_name)
        return True

    async def delete_session_collection(self, session_id: str) -> bool:
        return await asyncio.to_thread(self._delete_collection_sync, session_id)

    def add_documents_sync(
        self, session_id: str, chunks: list[str], source_file: str = "uploaded.pdf"
    ) -> int:
        self._create_collection_sync(session_id)
        client = self._get_sync_client()
        collection = client.collections.get(self._class_name(session_id))

        if self._embeddings is None:
            self._embeddings = GoogleGenerativeAIEmbeddings(
                model="models/embedding-001"
            )
        vectors = self._embeddings.embed_documents(chunks)

        with collection.batch.dynamic() as batch:
            for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
                batch.add_object(
                    properties={
                        "content": chunk,
                        "chunk_index": i,
                        "source_file": source_file,
                    },
                    vector=vector,
                )

        log.info("documents added", session_id=session_id, count=len(chunks))
        return len(chunks)

    async def add_documents(
        self, session_id: str, chunks: list[str], source_file: str = "uploaded.pdf"
    ) -> int:
        return await asyncio.to_thread(
            self.add_documents_sync, session_id, chunks, source_file
        )

    def similarity_search_sync(
        self, session_id: str, query: str, k: int = 4
    ) -> list[dict]:
        client = self._get_sync_client()
        class_name = self._class_name(session_id)
        if not client.collections.exists(class_name):
            return []

        collection = client.collections.get(class_name)
        if self._embeddings is None:
            self._embeddings = GoogleGenerativeAIEmbeddings(
                model="models/embedding-001"
            )
        query_vector = self._embeddings.embed_query(query)
        results = collection.query.near_vector(
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

    async def similarity_search(
        self, session_id: str, query: str, k: int = 4
    ) -> list[dict]:
        return await asyncio.to_thread(
            self.similarity_search_sync, session_id, query, k
        )

    def get_all_documents_sync(self, session_id: str) -> list[dict]:
        client = self._get_sync_client()
        class_name = self._class_name(session_id)
        if not client.collections.exists(class_name):
            return []

        collection = client.collections.get(class_name)
        docs = [
            {
                "content": obj.properties.get("content", ""),
                "chunk_index": obj.properties.get("chunk_index", 0),
                "source_file": obj.properties.get("source_file", ""),
            }
            for obj in collection.iterator()
        ]
        docs.sort(key=lambda x: x["chunk_index"])
        return docs

    async def get_all_documents(self, session_id: str) -> list[dict]:
        return await asyncio.to_thread(self.get_all_documents_sync, session_id)

    def collection_exists_sync(self, session_id: str) -> bool:
        client = self._get_sync_client()
        return client.collections.exists(self._class_name(session_id))

    async def collection_exists(self, session_id: str) -> bool:
        return await asyncio.to_thread(self.collection_exists_sync, session_id)

    def list_collections_sync(self) -> list[str]:
        client = self._get_sync_client()
        collections = client.collections.list_all()
        return [
            name.replace("Session_", "").replace("_", "-")
            for name in collections
            if name.startswith("Session_")
        ]

    async def list_collections(self) -> list[str]:
        return await asyncio.to_thread(self.list_collections_sync)


vectorstore_manager = VectorStoreManager()
