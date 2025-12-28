import logging
from typing import Optional

import weaviate
from weaviate.classes.config import Configure, Property, DataType
from weaviate.classes.query import MetadataQuery
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from backend.core.config import settings

logger = logging.getLogger(__name__)


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
            self._client = weaviate.connect_to_custom(
                http_host=host,
                http_port=port,
                http_secure=settings.weaviate_url.startswith("https"),
                grpc_host=host,
                grpc_port=50051,
                grpc_secure=settings.weaviate_url.startswith("https"),
            )

        self._embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
        self._initialized = True
        logger.info("Vector store manager initialized")

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

    async def create_session_collection(self, session_id: str) -> None:
        class_name = self._class_name(session_id)
        if self.client.collections.exists(class_name):
            return

        self.client.collections.create(
            name=class_name,
            vectorizer_config=Configure.Vectorizer.none(),
            properties=[
                Property(name="content", data_type=DataType.TEXT),
                Property(name="chunk_index", data_type=DataType.INT),
                Property(name="source_file", data_type=DataType.TEXT),
            ],
        )
        logger.info(f"Created collection: {class_name}")

    async def delete_session_collection(self, session_id: str) -> bool:
        class_name = self._class_name(session_id)
        if not self.client.collections.exists(class_name):
            return False
        self.client.collections.delete(class_name)
        logger.info(f"Deleted collection: {class_name}")
        return True

    async def add_documents(
        self, session_id: str, chunks: list[str], source_file: str = "uploaded.pdf"
    ) -> int:
        await self.create_session_collection(session_id)
        collection = self.client.collections.get(self._class_name(session_id))
        vectors = self.embeddings.embed_documents(chunks)

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

        logger.info(f"Added {len(chunks)} chunks for session {session_id}")
        return len(chunks)

    async def similarity_search(
        self, session_id: str, query: str, k: int = 4
    ) -> list[dict]:
        class_name = self._class_name(session_id)
        if not self.client.collections.exists(class_name):
            return []

        collection = self.client.collections.get(class_name)
        query_vector = self.embeddings.embed_query(query)
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

    async def get_all_documents(self, session_id: str) -> list[dict]:
        class_name = self._class_name(session_id)
        if not self.client.collections.exists(class_name):
            return []

        collection = self.client.collections.get(class_name)
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

    async def collection_exists(self, session_id: str) -> bool:
        return self.client.collections.exists(self._class_name(session_id))

    async def list_collections(self) -> list[str]:
        collections = self.client.collections.list_all()
        return [
            name.replace("Session_", "").replace("_", "-")
            for name in collections
            if name.startswith("Session_")
        ]


vectorstore_manager = VectorStoreManager()
