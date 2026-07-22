import pytest

from src.rag import KnowledgeBase, KnowledgeDocument, LLMClient, RAGEngine


class FakeLLMClient:
    """Stands in for LLMClient in tests -- no network calls, no API key needed."""

    def __init__(self, json_response=None, text_response=""):
        self.json_response = json_response
        self.text_response = text_response
        self.last_prompt = None

    def generate(self, prompt, max_tokens=512):
        self.last_prompt = prompt
        return self.text_response

    def generate_json(self, prompt, max_tokens=512):
        self.last_prompt = prompt
        return self.json_response


def make_knowledge_base():
    return KnowledgeBase([
        KnowledgeDocument(id="genre-pop", text="Pop is bright and upbeat.", source="test", tags=["pop", "upbeat"]),
        KnowledgeDocument(id="genre-lofi", text="Lofi is mellow and cozy.", source="test", tags=["lofi", "chill", "cozy"]),
        KnowledgeDocument(id="genre-metal", text="Metal is loud and aggressive.", source="test", tags=["metal", "aggressive"]),
    ])


def test_retrieve_finds_doc_by_tag_overlap():
    kb = make_knowledge_base()
    results = kb.retrieve("I want something upbeat and poppy", k=2)

    assert results
    assert results[0].id == "genre-pop"


def test_retrieve_returns_empty_when_no_overlap():
    kb = make_knowledge_base()
    assert kb.retrieve("xyzzy plugh quux", k=3) == []


def test_retrieve_respects_k():
    kb = make_knowledge_base()
    results = kb.retrieve("music genre mood", k=0)
    assert results == []


def test_knowledge_base_loads_real_catalog_file():
    kb = KnowledgeBase.load()
    assert len(kb.documents) > 0
    results = kb.retrieve("upbeat happy pop")
    assert any(doc.id == "genre-pop" for doc in results)


def test_generate_json_parses_plain_json():
    client = LLMClient()
    client.generate = lambda prompt, max_tokens=512: '{"genre": "pop", "mood": "happy"}'

    parsed = client.generate_json("irrelevant prompt")
    assert parsed == {"genre": "pop", "mood": "happy"}


def test_generate_json_parses_fenced_json():
    client = LLMClient()
    client.generate = lambda prompt, max_tokens=512: '```json\n{"genre": "lofi"}\n```'

    parsed = client.generate_json("irrelevant prompt")
    assert parsed == {"genre": "lofi"}


def test_generate_json_raises_value_error_on_garbage():
    client = LLMClient()
    client.generate = lambda prompt, max_tokens=512: "not json at all"

    with pytest.raises(ValueError):
        client.generate_json("irrelevant prompt")


def test_llm_client_raises_clear_error_without_api_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    client = LLMClient()

    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        client.generate("hello")


def test_parse_taste_query_returns_profile_and_sources():
    fake_llm = FakeLLMClient(json_response={"genre": "pop", "mood": "happy", "energy": 0.8})
    engine = RAGEngine(knowledge_base=make_knowledge_base(), llm_client=fake_llm)

    result = engine.parse_taste_query("something upbeat and poppy")

    assert result.profile == {"genre": "pop", "mood": "happy", "energy": 0.8}
    assert "genre-pop" in result.sources
    assert "pop" in fake_llm.last_prompt.lower()


def test_explain_with_context_returns_text_and_sources():
    fake_llm = FakeLLMClient(text_response="  This matches your love of upbeat pop.  ")
    engine = RAGEngine(knowledge_base=make_knowledge_base(), llm_client=fake_llm)

    result = engine.explain_with_context(
        "Sunrise City", "Neon Echo", "Genre match (pop vs pop): +30 pts", k=2,
    )

    assert result.text == "This matches your love of upbeat pop."
    assert result.sources
    assert "Sunrise City" in fake_llm.last_prompt
