from investigator.validate_suite import quality_violations


def row(name, outcome, bug=None, phase="call"):
    return dict(test_name=name, outcome=outcome, expected_bug=bug, phase=phase)


def test_declared_defect_and_healthy_test_are_accepted():
    assert not quality_violations(dict(test_count=2, outcomes=[row("bug", "failed", "BUG-01"), row("healthy", "passed")]))


def test_swapped_failure_is_rejected_even_when_counts_match():
    errors = quality_violations(dict(test_count=2, outcomes=[row("bug", "passed", "BUG-01"), row("healthy", "failed")]))
    assert len(errors) == 2


def test_skipped_test_is_rejected():
    assert quality_violations(dict(test_count=1, outcomes=[row("test", "skipped")]))


def test_setup_failure_and_missing_execution_are_rejected():
    assert quality_violations(dict(test_count=1, outcomes=[row("test", "failed", phase="setup")]))


def test_teardown_failure_is_rejected():
    assert quality_violations(dict(test_count=1, outcomes=[row("test", "passed"), row("test", "failed", phase="teardown")]))


def test_old_report_without_outcomes_is_rejected():
    assert quality_violations(dict(test_count=1))
