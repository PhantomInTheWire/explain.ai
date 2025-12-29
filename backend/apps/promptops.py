import json
import asyncio

from langchain.chains.question_answering import load_qa_chain
from langchain.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import Document

from core.vectorstore import vectorstore_manager
from core.session import session_manager
from core.logging import get_logger

log = get_logger(__name__)


def get_conversational_chain():
    prompt_template = """Answer the question as detailed as possible from the provided context.
    Context:\\n {context}?\\n Question: \\n{question}\\n
    Answer:
    """
    model = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0.5)
    prompt = PromptTemplate(
        template=prompt_template, input_variables=["context", "question"]
    )
    return load_qa_chain(model, chain_type="stuff", prompt=prompt)


async def process_user_question(session_id: str, user_question: str) -> str:
    if not user_question:
        raise ValueError("Question cannot be empty")

    results = await vectorstore_manager.similarity_search(
        session_id=session_id, query=user_question, k=4
    )
    if not results:
        raise ValueError("No documents found. Please upload a PDF first.")

    docs = [
        Document(page_content=r["content"], metadata={"chunk_index": r["chunk_index"]})
        for r in results
    ]
    chain = get_conversational_chain()
    response = await chain.ainvoke({"input_documents": docs, "question": user_question})
    return response["output_text"]


async def get_session_json_slide(session_id: str) -> dict | None:
    try:
        redis = session_manager.redis
        data = await redis.hget(f"session:{session_id}", "json_slide")
        return json.loads(data) if data else None
    except Exception:
        return None


async def set_session_json_slide(session_id: str, json_data: dict) -> None:
    redis = session_manager.redis
    await redis.hset(f"session:{session_id}", "json_slide", json.dumps(json_data))


async def generate_explanations(session_id: str) -> str:
    json_slides = await get_session_json_slide(session_id)
    if not json_slides:
        raise ValueError("No slide data found. Generate presentation first.")

    all_docs = await vectorstore_manager.get_all_documents(session_id)
    context_text = "\\n".join([doc["content"] for doc in all_docs[:10]])

    prompt = f"""You are given slide data for a classroom lecture:
{json.dumps(json_slides)}

Source material:
<{context_text}>

Act as a skilled teacher. Generate detailed explanations for each slide.
Output JSON format with keys "slide1", "slide2", etc.
Make explanations coherent when heard in sequence. Avoid "this slide explains..." phrases.
Output valid JSON only that can be parsed with json.loads()."""

    model = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0.7)
    result = await model.ainvoke(prompt)
    response_str = str(result.content).strip()

    if response_str.startswith("```json"):
        response_str = response_str[7:]
    if response_str.startswith("```"):
        response_str = response_str[3:]
    if response_str.endswith("```"):
        response_str = response_str[:-3]

    return response_str.strip()
