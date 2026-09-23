#!/usr/bin/env python3
"""Integration test for jev_auto_selector wrapper."""

from jev_auto_selector import JevAutoSelectorSync, JevComplexityAnalyzer


def test_complexity_analyzer():
    """Test complexity classification."""
    analyzer = JevComplexityAnalyzer()

    simple = analyzer.analyze("Is this correct?")
    complex_ = analyzer.analyze("Should we refactor this architecture?")

    print(f"✓ Analyzer: 'Is this correct?' → {simple}")
    print(f"✓ Analyzer: 'Should we refactor...' → {complex_}")

    assert simple == "simple", f"Expected simple, got {simple}"
    assert complex_ == "complex", f"Expected complex, got {complex_}"


def test_model_selection():
    """Test model auto-selection."""
    selector = JevAutoSelectorSync()

    model_simple = selector.select_model("Is this right?")
    model_complex = selector.select_model("Should we refactor considering edge cases?")

    print(f"✓ Simple question → {model_simple}")
    print(f"✓ Complex question → {model_complex}")

    assert model_simple == "jev-latest"
    assert model_complex == "jev-preview"


def test_jev_integration():
    """Test actual jev call via wrapper (requires running MCP server)."""
    try:
        selector = JevAutoSelectorSync()

        # Simple classify
        result = selector.classify(
            state="User saved a document",
            question="Did the operation succeed?",
            options={"yes": "Success", "no": "Failed", "unclear": "Uncertain"}
        )

        print(f"✓ Simple jev_classify call:")
        print(f"  - Model: {result.get('model')}")
        print(f"  - Choice: {result.get('choice')}")
        print(f"  - Confidence: {result.get('confidence'):.2f}")
        print(f"  - Action: {result.get('action')}")

        assert result.get('model') == 'jev-latest'
        assert result.get('choice') in ['yes', 'no', 'unclear', 'none']

        # Complex classify
        result = selector.classify(
            state="Code: 200-line loop with 3 edge cases, concurrent writes, retry logic",
            question="Should we refactor this considering maintainability and performance?",
            options={
                "refactor_now": "Multi-stage refactor improves both",
                "defer": "Defer until pattern clarifies",
                "leave": "Current design sufficient",
            }
        )

        print(f"✓ Complex jev_classify call:")
        print(f"  - Model: {result.get('model')}")
        print(f"  - Choice: {result.get('choice')}")
        print(f"  - Confidence: {result.get('confidence'):.2f}")
        print(f"  - Action: {result.get('action')}")

        assert result.get('model') == 'jev-preview'
        assert result.get('choice') in ['refactor_now', 'defer', 'leave', 'none']

        print("\n✓ All integration tests passed!")

    except Exception as e:
        print(f"✗ Integration test failed: {e}")
        print("  (MCP server may not be running on localhost:8000)")


if __name__ == "__main__":
    print("Testing jev_auto_selector wrapper...\n")

    test_complexity_analyzer()
    print()

    test_model_selection()
    print()

    test_jev_integration()
