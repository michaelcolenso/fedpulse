from pathlib import Path


def test_nightly_semantic_stats_use_bootstrap_contract() -> None:
    workflow = Path(".github/workflows/nightly.yml").read_text(encoding="utf-8")

    assert '["unchanged"]' in workflow
    assert '["skipped"]' not in workflow
    assert '$unchanged unchanged' in workflow


def test_nightly_has_only_permanent_triggers() -> None:
    workflow = Path(".github/workflows/nightly.yml").read_text(encoding="utf-8")

    assert "schedule:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "\n  push:\n" not in workflow
