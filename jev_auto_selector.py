"""Jev model auto-selector based on task complexity."""

import json
import os
import re
import urllib.request
import urllib.error
from typing import Any, Literal, Optional


class JevComplexityAnalyzer:
    """Analyzes prompt/question complexity to select appropriate model."""

    SIMPLE_KEYWORDS = {
        'pick', 'choose', 'select', 'yes', 'no', 'is', 'should',
        'one', 'best', 'right', 'which', 'what'
    }

    COMPLEX_KEYWORDS = {
        'tradeoff', 'consider', 'multi', 'edge', 'corner', 'constraint',
        'refactor', 'architecture', 'design', 'pattern', 'integrate',
        'performance', 'security', 'reliability', 'scale', 'migration'
    }

    def __init__(self):
        self.simple_threshold = 15  # words
        self.complex_threshold = 50  # words

    def analyze(self, prompt: str) -> Literal["simple", "complex"]:
        """Classify prompt complexity: simple → jev-latest, complex → jev-preview."""
        word_count = len(prompt.split())

        # Quick heuristics
        has_complex_keywords = bool(
            set(prompt.lower().split()) & self.COMPLEX_KEYWORDS
        )
        has_multiple_parts = prompt.count('?') > 1 or prompt.count(';') > 0
        has_code = bool(re.search(r'```|def |class |import ', prompt))

        if has_complex_keywords or has_code or has_multiple_parts:
            return "complex"

        if word_count <= self.simple_threshold:
            return "simple"

        if word_count >= self.complex_threshold:
            return "complex"

        return "simple"


class JevAutoSelectorSync:
    """Sync wrapper for jev that auto-selects model based on complexity."""

    MODEL_MAP = {
        "simple": "jev-latest",
        "complex": "jev-preview",
    }

    def __init__(self, api_key: Optional[str] = None, base_url: str = "http://localhost:8000"):
        self.api_key = api_key or os.getenv("JEV_API_KEY", "")
        self.base_url = base_url
        self.analyzer = JevComplexityAnalyzer()

    def select_model(self, prompt: str) -> str:
        """Select model based on prompt complexity."""
        complexity = self.analyzer.analyze(prompt)
        model = self.MODEL_MAP[complexity]
        return model

    def classify(
        self,
        state: Any,
        question: str,
        options: dict[str, Any],
        act_above: float = 0.8,
        review_above: float = 0.5,
        add_none: bool = True,
    ) -> dict[str, Any]:
        """Classify with auto-selected model."""
        model = self.select_model(question)

        payload = {
            "state": state,
            "question": question,
            "options": options,
            "act_above": act_above,
            "review_above": review_above,
            "add_none": add_none,
            "model": model,
        }

        return self._call_jev("classify", payload)

    def score(
        self,
        state: Any,
        question: str,
        levels: list[str],
        act_above: float = 0.8,
        review_above: float = 0.5,
    ) -> dict[str, Any]:
        """Score with auto-selected model."""
        model = self.select_model(question)

        payload = {
            "state": state,
            "question": question,
            "levels": levels,
            "act_above": act_above,
            "review_above": review_above,
            "model": model,
        }

        return self._call_jev("score", payload)

    def check(
        self,
        state: Any,
        question: str,
    ) -> dict[str, Any]:
        """Check with auto-selected model."""
        model = self.select_model(question)

        payload = {
            "state": state,
            "question": question,
            "model": model,
        }

        return self._call_jev("check", payload)

    def ask(
        self,
        state: Any,
        questions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Ask batch of questions with auto-selected model."""
        # Use first question for complexity analysis
        first_q = json.dumps(questions[0].get("question", ""))
        model = self.select_model(first_q)

        payload = {
            "state": state,
            "questions": questions,
            "model": model,
        }

        return self._call_jev("ask", payload)

    def _call_jev(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Make HTTP call to jev MCP server using urllib."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        url = f"{self.base_url}/jev/{endpoint}"
        data = json.dumps(payload).encode('utf-8')

        req = urllib.request.Request(url, data=data, headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"jev HTTP error: {e.code} {e.reason}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"jev connection error: {e.reason}") from e


# Test
if __name__ == "__main__":
    analyzer = JevComplexityAnalyzer()

    # Test complexity analysis
    tests = [
        ("yes?", "simple"),
        ("Is this right?", "simple"),
        ("Should we refactor this?", "complex"),
        ("Should we refactor considering tradeoffs?", "complex"),
        ("Should we refactor this multi-threaded code considering performance, security, and maintainability?", "complex"),
    ]

    for prompt, expected in tests:
        result = analyzer.analyze(prompt)
        status = "✓" if result == expected else "✗"
        print(f"{status} '{prompt}' → {result} (expected {expected})")
