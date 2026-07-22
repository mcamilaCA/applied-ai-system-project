"""
Retrieval-Augmented Generation layer for Tunefy.

Two use cases, both grounded in the same small local knowledge base
(`data/knowledge_base.json`) instead of letting an LLM answer purely from its
own training data:

1. `RAGEngine.parse_taste_query` turns a free-text taste description
   ("upbeat, nostalgic, early-2000s pop") into a raw preferences dict shaped
   exactly like the one `src/planner.py`'s `plan_user_prefs` already
   validates, so a malformed or invalid field coming out of the LLM gets the
   same Notice/PlanningError handling a manually-typed profile would --
   no separate validation path, no changes to recommender.py/planner.py.
2. `RAGEngine.explain_with_context` turns an existing deterministic score
   breakdown (the per-feature reasons text `score_song`/`recommend_songs`
   already produce) into a short natural-language paragraph, using
   retrieved genre/mood/artist notes as its only source of extra detail so
   it can't invent facts the reasons didn't already establish.
"""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

DEFAULT_MODEL = "claude-haiku-4-5-20251001"

KNOWLEDGE_BASE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "knowledge_base.json")

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> List[str]:
    return _WORD_RE.findall(text.lower())


@dataclass
class KnowledgeDocument:
    id: str
    text: str
    source: str
    tags: List[str] = field(default_factory=list)


class KnowledgeBase:
    """
    Small local reference corpus (genre/mood/artist notes), retrieved by
    keyword/tag overlap rather than embeddings. No new ML dependency, and it
    keeps retrieval inspectable -- consistent with how the rest of this
    project explains itself with plain, checkable reasons rather than an
    opaque similarity score.
    """

    def __init__(self, documents: List[KnowledgeDocument]):
        self.documents = documents

    @classmethod
    def load(cls, path: str = KNOWLEDGE_BASE_PATH) -> "KnowledgeBase":
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return cls([KnowledgeDocument(**doc) for doc in raw])

    def retrieve(self, query: str, k: int = 4) -> List[KnowledgeDocument]:
        """
        Returns up to k documents ranked by token overlap with `query`.
        Documents with zero overlapping tokens are excluded rather than
        padding the result with irrelevant docs.
        """
        query_tokens = set(_tokenize(query))
        if not query_tokens:
            return []

        scored = []
        for doc in self.documents:
            doc_tokens = set(_tokenize(doc.text)) | set(_tokenize(" ".join(doc.tags)))
            overlap = len(query_tokens & doc_tokens)
            if overlap:
                scored.append((overlap, doc))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [doc for _, doc in scored[:k]]


class LLMClient:
    """
    Thin wrapper around the Anthropic client.

    The real `anthropic.Anthropic()` client is constructed lazily, on first
    use, not in __init__ -- so importing this module (from app.py, main.py,
    or during pytest collection) never fails just because the `anthropic`
    package or ANTHROPIC_API_KEY isn't available. Only actually calling
    `generate`/`generate_json` without a key raises, with a clear message:
    the same "fail loudly, but only when it actually matters" approach
    already used for PlanningError in planner.py.
    """

    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise RuntimeError(
                    "ANTHROPIC_API_KEY is not set. Export it before using the "
                    "natural-language taste box or grounded explanations -- "
                    "the structured profile form doesn't need it."
                )
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def generate(self, prompt: str, max_tokens: int = 512) -> str:
        client = self._get_client()
        response = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def generate_json(self, prompt: str, max_tokens: int = 512) -> Dict[str, Any]:
        """
        Calls `generate` and parses the result as JSON, tolerating a
        ```json ... ``` fenced block around the object (a common model
        habit even when told not to). Raises ValueError with the raw text
        on failure so callers can decide how to degrade instead of getting
        an opaque JSONDecodeError.
        """
        raw = self.generate(prompt, max_tokens=max_tokens)
        candidate = raw.strip()
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", candidate, re.DOTALL)
        if fence_match:
            candidate = fence_match.group(1)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as error:
            raise ValueError(f"LLM did not return valid JSON: {raw!r}") from error


@dataclass
class ParsedTasteResult:
    """Output of RAGEngine.parse_taste_query. `sources` lists the knowledge doc ids used to ground the parse."""
    profile: Dict[str, Any]
    sources: List[str]
    raw_response: str


@dataclass
class RAGExplanation:
    """Output of RAGEngine.explain_with_context. `sources` lists the knowledge doc ids the explanation drew on."""
    text: str
    sources: List[str]


_PROFILE_FIELDS_NOTE = (
    "Only use these keys, all optional except genre and mood: "
    "genre (str), mood (str), energy (float 0-1), likes_acoustic (bool), "
    "preferred_decade (str like \"1990s\"/\"2000s\"/\"2010s\"/\"2020s\", omit if not mentioned), "
    "wants_instrumental (bool, omit if not mentioned), clean_only (bool), prefer_popular (bool). "
    "Omit any key the listener didn't express an opinion about -- do not guess a value for it."
)


class RAGEngine:
    def __init__(self, knowledge_base: KnowledgeBase, llm_client: LLMClient):
        self.knowledge_base = knowledge_base
        self.llm_client = llm_client

    def parse_taste_query(self, nl_query: str, k: int = 4) -> ParsedTasteResult:
        docs = self.knowledge_base.retrieve(nl_query, k=k)
        context = "\n".join(f"- {doc.text}" for doc in docs) or "(no matching reference docs found)"
        prompt = (
            "You are translating a listener's free-text music taste description into a "
            "structured preferences JSON object for a recommender system.\n\n"
            f"Reference vocabulary (use this to interpret words like \"upbeat\" or \"retro\"):\n{context}\n\n"
            f"{_PROFILE_FIELDS_NOTE}\n\n"
            "Respond with ONLY the JSON object, no other text.\n\n"
            f"Listener's description: {nl_query!r}"
        )
        profile = self.llm_client.generate_json(prompt)
        return ParsedTasteResult(
            profile=profile,
            sources=[doc.id for doc in docs],
            raw_response=json.dumps(profile),
        )

    def explain_with_context(self, song_title: str, artist: str, reasons_text: str, k: int = 3) -> RAGExplanation:
        docs = self.knowledge_base.retrieve(f"{song_title} {artist} {reasons_text}", k=k)
        context = "\n".join(f"- {doc.text}" for doc in docs) or "(no matching reference docs found)"
        prompt = (
            "Write a short (2-3 sentence), friendly explanation of why this song was "
            "recommended to a listener. Base every claim ONLY on the score breakdown and "
            "reference notes below -- do not invent details about the song or artist that "
            "aren't supported by them.\n\n"
            f"Song: {song_title} by {artist}\n\n"
            f"Score breakdown:\n{reasons_text}\n\n"
            f"Reference notes:\n{context}\n\n"
            "Respond with ONLY the explanation text."
        )
        text = self.llm_client.generate(prompt).strip()
        return RAGExplanation(text=text, sources=[doc.id for doc in docs])
