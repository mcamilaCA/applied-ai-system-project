"""
Reliability harness for Tunefy's AI surfaces.

The deterministic core (`Recommender`/`score_song`) doesn't need this -- same
input always gives the same output, and `tests/test_recommender.py` already
covers it. It's the two RAG paths in `src/rag.py` that need a check: an LLM
call means the same natural-language query or the same score breakdown can
produce a *different* answer each time, and it can also produce an answer
that sounds plausible but isn't actually backed by anything retrieved.

This module runs a small set of golden cases (`data/eval_cases.json`) through
one of three checks depending on `EvalCase.kind`:

- "profile_score": a regression guard on the deterministic core -- exact
  top-song match, no LLM involved.
- "nl_parse": runs `RAGEngine.parse_taste_query`, checks the parsed profile
  against `expected`, and measures how *consistent* repeated parses of the
  same query are (`ConsistencyChecker`).
- "explanation": runs `RAGEngine.explain_with_context`, measures how
  *grounded* the generated text is in what it was allowed to draw on
  (`GroundednessChecker`), and how consistent repeated generations are.

Run with:
    python -m src.reliability
"""

import itertools
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

try:
    from recommender import load_songs, recommend_songs, score_song
    from planner import PlanningError
    from rag import KnowledgeBase, LLMClient, RAGEngine
except ImportError:
    from src.recommender import load_songs, recommend_songs, score_song
    from src.planner import PlanningError
    from src.rag import KnowledgeBase, LLMClient, RAGEngine

SONGS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "songs.csv")
EVAL_CASES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "eval_cases.json")
REPORT_PATH = os.path.join(os.path.dirname(__file__), "..", "logs", "reliability_report.md")

_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "this", "that", "it", "to",
    "of", "in", "on", "for", "and", "or", "but", "your", "you", "with", "as",
    "by", "be", "has", "have", "had", "its", "from", "at", "so", "not", "no",
    "do", "does", "will", "than",
}


def _tokenize(text: str) -> List[str]:
    return _WORD_RE.findall(text.lower())


@dataclass
class EvalCase:
    id: str
    kind: str
    input: Dict[str, Any]
    expected: Dict[str, Any]


@dataclass
class EvalResult:
    case_id: str
    kind: str
    passed: bool
    actual: Any
    notes: str
    consistency: Optional[float] = None
    groundedness: Optional[float] = None


@dataclass
class EvalReport:
    results: List[EvalResult]
    pass_rate: float
    avg_consistency: Optional[float]
    avg_groundedness: Optional[float]

    def to_markdown(self) -> str:
        passed_count = sum(1 for r in self.results if r.passed)
        lines = [
            "# Reliability Report",
            "",
            f"- Pass rate: {self.pass_rate:.0%} ({passed_count}/{len(self.results)})",
        ]
        if self.avg_consistency is not None:
            lines.append(f"- Avg consistency (LLM-backed cases): {self.avg_consistency:.2f}")
        if self.avg_groundedness is not None:
            lines.append(f"- Avg groundedness (LLM-backed cases): {self.avg_groundedness:.2f}")
        lines += [
            "",
            "| Case | Kind | Passed | Consistency | Groundedness | Notes |",
            "|---|---|---|---|---|---|",
        ]
        for r in self.results:
            consistency = f"{r.consistency:.2f}" if r.consistency is not None else "-"
            groundedness = f"{r.groundedness:.2f}" if r.groundedness is not None else "-"
            lines.append(
                f"| {r.case_id} | {r.kind} | {'✅' if r.passed else '❌'} | "
                f"{consistency} | {groundedness} | {r.notes} |"
            )
        return "\n".join(lines)


class ConsistencyChecker:
    """
    Reruns the same call `runs` times and scores agreement. Two modes:
    - `key` given: exact-match agreement rate on that key across dict outputs
      (used for `parse_taste_query`, where "genre"/"mood" should be stable).
    - `key` omitted: average pairwise token-overlap (Jaccard) similarity
      across free-text outputs (used for `explain_with_context`, where exact
      text equality isn't a realistic bar for generated prose).
    """

    def measure(self, fn: Callable[[Any], Any], input: Any, runs: int = 3, key: Optional[str] = None) -> float:
        outputs = [fn(input) for _ in range(runs)]

        if key is not None:
            values = [output.get(key) if isinstance(output, dict) else None for output in outputs]
            if not values:
                return 0.0
            most_common_count = max(values.count(v) for v in set(values))
            return most_common_count / len(values)

        texts = [output if isinstance(output, str) else str(output) for output in outputs]
        token_sets = [set(_tokenize(text)) for text in texts]
        pairs = list(itertools.combinations(range(len(token_sets)), 2))
        if not pairs:
            return 1.0
        similarities = []
        for i, j in pairs:
            union = token_sets[i] | token_sets[j]
            intersection = token_sets[i] & token_sets[j]
            similarities.append(len(intersection) / len(union) if union else 1.0)
        return sum(similarities) / len(similarities)


class GroundednessChecker:
    """
    Scores what fraction of a generated text's non-trivial words also appear
    in the context it was supposed to be grounded on (retrieved knowledge
    docs plus, for explanations, the deterministic score breakdown). This is
    a keyword-overlap heuristic, not an LLM judge -- deliberately, so the
    checker itself stays deterministic and testable without another live
    API call.
    """

    def check(self, text: str, context_text: str) -> float:
        claim_tokens = [t for t in _tokenize(text) if t not in _STOPWORDS and not t.isdigit()]
        if not claim_tokens:
            return 1.0
        context_tokens = set(_tokenize(context_text))
        grounded = sum(1 for token in claim_tokens if token in context_tokens)
        return grounded / len(claim_tokens)


class ReliabilityHarness:
    def __init__(self, cases: List[EvalCase], songs: List[Dict], rag_engine: RAGEngine, consistency_runs: int = 3):
        self.cases = cases
        self.songs = songs
        self.rag_engine = rag_engine
        self.consistency_runs = consistency_runs
        self.consistency_checker = ConsistencyChecker()
        self.groundedness_checker = GroundednessChecker()

    @classmethod
    def load(
        cls,
        cases_path: str = EVAL_CASES_PATH,
        songs_path: str = SONGS_PATH,
        rag_engine: Optional[RAGEngine] = None,
        consistency_runs: int = 3,
    ) -> "ReliabilityHarness":
        with open(cases_path, encoding="utf-8") as f:
            raw_cases = json.load(f)
        cases = [EvalCase(**case) for case in raw_cases]
        songs = load_songs(songs_path)
        if rag_engine is None:
            rag_engine = RAGEngine(knowledge_base=KnowledgeBase.load(), llm_client=LLMClient())
        return cls(cases=cases, songs=songs, rag_engine=rag_engine, consistency_runs=consistency_runs)

    def run_all(self) -> EvalReport:
        results = [self.run_case(case) for case in self.cases]
        pass_rate = sum(1 for r in results if r.passed) / len(results) if results else 0.0
        consistencies = [r.consistency for r in results if r.consistency is not None]
        groundednesses = [r.groundedness for r in results if r.groundedness is not None]
        return EvalReport(
            results=results,
            pass_rate=pass_rate,
            avg_consistency=sum(consistencies) / len(consistencies) if consistencies else None,
            avg_groundedness=sum(groundednesses) / len(groundednesses) if groundednesses else None,
        )

    def run_case(self, case: EvalCase) -> EvalResult:
        if case.kind == "profile_score":
            return self._run_profile_score_case(case)
        if case.kind == "nl_parse":
            return self._run_nl_parse_case(case)
        if case.kind == "explanation":
            return self._run_explanation_case(case)
        raise ValueError(f"Unknown eval case kind: {case.kind!r}")

    def _run_profile_score_case(self, case: EvalCase) -> EvalResult:
        try:
            results, _ = recommend_songs(case.input["user_prefs"], self.songs, k=1)
        except PlanningError as error:
            return EvalResult(case_id=case.id, kind=case.kind, passed=False, actual=None, notes=f"PlanningError: {error}")

        actual_top_id = results[0][0]["id"] if results else None
        passed = actual_top_id == case.expected.get("top_song_id")
        return EvalResult(
            case_id=case.id, kind=case.kind, passed=passed, actual=actual_top_id,
            notes="deterministic, no LLM call",
        )

    def _run_nl_parse_case(self, case: EvalCase) -> EvalResult:
        nl_query = case.input["nl_query"]
        try:
            parsed = self.rag_engine.parse_taste_query(nl_query)
        except (RuntimeError, ValueError) as error:
            return EvalResult(case_id=case.id, kind=case.kind, passed=False, actual=None, notes=str(error))

        passed = all(parsed.profile.get(field_name) == value for field_name, value in case.expected.items())
        consistency_key = next(iter(case.expected), None)
        consistency = self.consistency_checker.measure(
            lambda query: self.rag_engine.parse_taste_query(query).profile,
            nl_query,
            runs=self.consistency_runs,
            key=consistency_key,
        )
        return EvalResult(
            case_id=case.id, kind=case.kind, passed=passed, actual=parsed.profile,
            notes=f"grounded on {', '.join(parsed.sources) or 'no docs'}",
            consistency=consistency,
        )

    def _run_explanation_case(self, case: EvalCase) -> EvalResult:
        song = next((s for s in self.songs if s["id"] == case.input["song_id"]), None)
        if song is None:
            return EvalResult(case_id=case.id, kind=case.kind, passed=False, actual=None, notes="song_id not found in catalog")

        _, reasons = score_song(case.input["user_prefs"], song)
        reasons_text = "\n".join(reasons)

        try:
            explanation = self.rag_engine.explain_with_context(song["title"], song["artist"], reasons_text)
        except (RuntimeError, ValueError) as error:
            return EvalResult(case_id=case.id, kind=case.kind, passed=False, actual=None, notes=str(error))

        source_docs_text = "\n".join(
            doc.text for doc in self.rag_engine.knowledge_base.documents if doc.id in explanation.sources
        )
        groundedness = self.groundedness_checker.check(explanation.text, reasons_text + "\n" + source_docs_text)
        passed = groundedness >= case.expected.get("min_groundedness", 0.5)
        consistency = self.consistency_checker.measure(
            lambda _: self.rag_engine.explain_with_context(song["title"], song["artist"], reasons_text).text,
            None,
            runs=self.consistency_runs,
        )
        return EvalResult(
            case_id=case.id, kind=case.kind, passed=passed, actual=explanation.text,
            notes=f"grounded on {', '.join(explanation.sources) or 'no docs'}",
            consistency=consistency, groundedness=groundedness,
        )


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "❌ ANTHROPIC_API_KEY is not set. The nl_parse/explanation cases need it "
            "to call the LLM -- export it and re-run."
        )
        return

    harness = ReliabilityHarness.load()
    report = harness.run_all()

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report.to_markdown())

    print(report.to_markdown())
    print(f"\nWritten to {REPORT_PATH}")


if __name__ == "__main__":
    main()
