import json

from src.rag import KnowledgeBase, KnowledgeDocument, ParsedTasteResult, RAGExplanation
from src.reliability import (
    ConsistencyChecker,
    EvalCase,
    EvalReport,
    EvalResult,
    GroundednessChecker,
    ReliabilityHarness,
)


class FakeRAGEngine:
    """Stands in for RAGEngine in tests -- no LLM calls, fully deterministic."""

    def __init__(self, profile=None, explanation_text="", sources=None, knowledge_base=None):
        self.profile = profile or {}
        self.explanation_text = explanation_text
        self.sources = sources or []
        self.knowledge_base = knowledge_base or KnowledgeBase([])

    def parse_taste_query(self, nl_query, k=4):
        return ParsedTasteResult(profile=dict(self.profile), sources=list(self.sources), raw_response=json.dumps(self.profile))

    def explain_with_context(self, song_title, artist, reasons_text, k=3):
        return RAGExplanation(text=self.explanation_text, sources=list(self.sources))


def make_songs():
    return [
        {
            "id": 1, "title": "Test Pop Track", "artist": "Test Artist", "genre": "pop", "mood": "happy",
            "energy": 0.8, "acousticness": 0.2, "danceability": 0.8,
        },
        {
            "id": 2, "title": "Chill Lofi Loop", "artist": "Test Artist", "genre": "lofi", "mood": "chill",
            "energy": 0.4, "acousticness": 0.9, "danceability": 0.5,
        },
    ]


# --- ConsistencyChecker ---

def test_consistency_checker_full_agreement_by_key():
    checker = ConsistencyChecker()
    score = checker.measure(lambda q: {"genre": "pop"}, "query", runs=4, key="genre")
    assert score == 1.0


def test_consistency_checker_partial_agreement_by_key():
    checker = ConsistencyChecker()
    outputs = iter([{"genre": "pop"}, {"genre": "pop"}, {"genre": "lofi"}])
    score = checker.measure(lambda q: next(outputs), "query", runs=3, key="genre")
    assert round(score, 2) == round(2 / 3, 2)


def test_consistency_checker_identical_text_scores_one():
    checker = ConsistencyChecker()
    score = checker.measure(lambda _: "this song matches your happy pop taste", None, runs=3)
    assert score == 1.0


def test_consistency_checker_disjoint_text_scores_zero():
    checker = ConsistencyChecker()
    outputs = iter(["alpha beta gamma", "delta epsilon zeta"])
    score = checker.measure(lambda _: next(outputs), None, runs=2)
    assert score == 0.0


# --- GroundednessChecker ---

def test_groundedness_checker_fully_grounded_text_scores_one():
    checker = GroundednessChecker()
    context = "Genre match pop vs pop. Mood match happy vs happy."
    score = checker.check("Genre match, mood match, pop, happy.", context)
    assert score == 1.0


def test_groundedness_checker_penalizes_unsupported_claims():
    checker = GroundednessChecker()
    context = "Genre match pop vs pop."
    score = checker.check("This matches your love of pop and features a saxophone solo.", context)
    assert 0.0 < score < 1.0


def test_groundedness_checker_empty_text_is_trivially_grounded():
    checker = GroundednessChecker()
    assert checker.check("", "some context") == 1.0


# --- EvalReport ---

def test_eval_report_to_markdown_includes_pass_rate_and_rows():
    report = EvalReport(
        results=[
            EvalResult(case_id="case-1", kind="profile_score", passed=True, actual=1, notes="ok"),
            EvalResult(case_id="case-2", kind="nl_parse", passed=False, actual={}, notes="mismatch", consistency=0.5),
        ],
        pass_rate=0.5,
        avg_consistency=0.5,
        avg_groundedness=None,
    )
    markdown = report.to_markdown()

    assert "50%" in markdown
    assert "case-1" in markdown and "case-2" in markdown
    assert "✅" in markdown and "❌" in markdown


# --- ReliabilityHarness ---

def test_profile_score_case_passes_on_correct_top_song():
    case = EvalCase(
        id="pop-happy", kind="profile_score",
        input={"user_prefs": {"genre": "pop", "mood": "happy", "energy": 0.8, "likes_acoustic": False}},
        expected={"top_song_id": 1},
    )
    harness = ReliabilityHarness(cases=[case], songs=make_songs(), rag_engine=FakeRAGEngine())

    result = harness.run_case(case)

    assert result.passed
    assert result.actual == 1
    assert result.consistency is None  # deterministic core, no consistency metric needed


def test_profile_score_case_fails_on_wrong_expectation():
    case = EvalCase(
        id="pop-happy-wrong", kind="profile_score",
        input={"user_prefs": {"genre": "pop", "mood": "happy", "energy": 0.8, "likes_acoustic": False}},
        expected={"top_song_id": 2},
    )
    harness = ReliabilityHarness(cases=[case], songs=make_songs(), rag_engine=FakeRAGEngine())

    result = harness.run_case(case)

    assert not result.passed


def test_nl_parse_case_uses_rag_engine_and_measures_consistency():
    case = EvalCase(
        id="nl-pop", kind="nl_parse",
        input={"nl_query": "upbeat pop please"},
        expected={"genre": "pop"},
    )
    fake_engine = FakeRAGEngine(profile={"genre": "pop", "mood": "happy"}, sources=["genre-pop"])
    harness = ReliabilityHarness(cases=[case], songs=[], rag_engine=fake_engine, consistency_runs=2)

    result = harness.run_case(case)

    assert result.passed
    assert result.actual == {"genre": "pop", "mood": "happy"}
    assert result.consistency == 1.0  # FakeRAGEngine always returns the same profile
    assert "genre-pop" in result.notes


def test_explanation_case_measures_groundedness():
    knowledge_base = KnowledgeBase([
        KnowledgeDocument(id="genre-pop", text="Pop is bright and upbeat.", source="test", tags=["pop"]),
    ])
    fake_engine = FakeRAGEngine(
        explanation_text="This song has a happy mood and pop genre.",
        sources=["genre-pop"],
        knowledge_base=knowledge_base,
    )
    case = EvalCase(
        id="explain-1", kind="explanation",
        input={"song_id": 1, "user_prefs": {"genre": "pop", "mood": "happy", "energy": 0.8, "likes_acoustic": False}},
        expected={"min_groundedness": 0.5},
    )
    harness = ReliabilityHarness(cases=[case], songs=make_songs(), rag_engine=fake_engine, consistency_runs=2)

    result = harness.run_case(case)

    assert result.groundedness is not None and result.groundedness > 0.5
    assert result.passed
    assert result.consistency == 1.0  # FakeRAGEngine always returns the same text


def test_explanation_case_fails_when_song_missing_from_catalog():
    case = EvalCase(
        id="explain-missing", kind="explanation",
        input={"song_id": 999, "user_prefs": {"genre": "pop", "mood": "happy", "energy": 0.8, "likes_acoustic": False}},
        expected={"min_groundedness": 0.5},
    )
    harness = ReliabilityHarness(cases=[case], songs=make_songs(), rag_engine=FakeRAGEngine())

    result = harness.run_case(case)

    assert not result.passed
    assert "not found" in result.notes
