import env
from openai import AsyncOpenAI

_openai = AsyncOpenAI(api_key=env.OPENAI_API_KEY)
_local_model = None

def get_local_model():
    global _local_model
    if _local_model is None:
        from sentence_transformers import SentenceTransformer
        _local_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _local_model

async def get_embedding(text: str) -> tuple[list[float], str]:
    """Returns (vector, model_name). Never raises — returns (None, 'none') on failure."""
    try:
        if env.LOCAL_EMBEDDINGS:
            model = get_local_model()
            return model.encode(text).tolist(), "all-MiniLM-L6-v2"
        response = await _openai.embeddings.create(
            input=text[:8000],
            model="text-embedding-3-small"
        )
        return response.data[0].embedding, "text-embedding-3-small"
    except Exception as e:
        import structlog
        structlog.get_logger().error("embedding_failed", error=str(e))
        return None, "none"
