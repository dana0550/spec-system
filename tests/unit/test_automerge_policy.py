from __future__ import annotations

from specctl.automerge_policy import CheckContext, evaluate_auto_merge, is_checkbox_checked, parse_csv


def test_parse_csv_handles_empty_and_whitespace() -> None:
    assert parse_csv(None) == ()
    assert parse_csv("") == ()
    assert parse_csv("  one, two , ,three ") == ("one", "two", "three")


def test_checkbox_detection_is_case_insensitive() -> None:
    body = """
    ## Auto-Merge
    - [x] Disable default auto-merge for this PR
    """
    assert is_checkbox_checked(body, "Disable default auto-merge for this PR")


def test_evaluate_auto_merge_allows_merge_when_everything_is_green() -> None:
    checks = [
        CheckContext(name="CI / test", kind="check_run", status="COMPLETED", conclusion="SUCCESS"),
        CheckContext(
            name="Cursor Bugbot",
            kind="check_run",
            status="COMPLETED",
            conclusion="SUCCESS",
            app_slug="cursor",
        ),
    ]
    decision = evaluate_auto_merge(
        state="OPEN",
        merged=False,
        is_draft=False,
        mergeable="MERGEABLE",
        body="",
        labels=[],
        checks=checks,
        unresolved_bugbot_threads=0,
        disable_label="automerge:off",
        disable_checkbox_label="Disable default auto-merge for this PR",
        ignored_check_prefixes=("Auto Merge /",),
        bugbot_check_keywords=("bugbot", "cursor"),
    )
    assert decision.should_merge is True
    assert decision.reasons == ()
    assert decision.disabled_reason is None


def test_evaluate_auto_merge_disables_when_label_is_present() -> None:
    decision = evaluate_auto_merge(
        state="OPEN",
        merged=False,
        is_draft=False,
        mergeable="MERGEABLE",
        body="",
        labels=["automerge:off"],
        checks=[],
        unresolved_bugbot_threads=0,
        disable_label="automerge:off",
        disable_checkbox_label="Disable default auto-merge for this PR",
        ignored_check_prefixes=(),
        bugbot_check_keywords=("bugbot",),
    )
    assert decision.should_merge is False
    assert decision.disabled_reason == "Label `automerge:off` is present."


def test_evaluate_auto_merge_disables_when_checkbox_is_checked() -> None:
    decision = evaluate_auto_merge(
        state="OPEN",
        merged=False,
        is_draft=False,
        mergeable="MERGEABLE",
        body="- [X] Disable default auto-merge for this PR\n",
        labels=[],
        checks=[],
        unresolved_bugbot_threads=0,
        disable_label="automerge:off",
        disable_checkbox_label="Disable default auto-merge for this PR",
        ignored_check_prefixes=(),
        bugbot_check_keywords=("bugbot",),
    )
    assert decision.should_merge is False
    assert decision.disabled_reason == "Checkbox `Disable default auto-merge for this PR` is checked."


def test_evaluate_auto_merge_blocks_when_bugbot_threads_are_unresolved() -> None:
    checks = [
        CheckContext(name="CI / test", kind="check_run", status="COMPLETED", conclusion="SUCCESS"),
        CheckContext(name="bugbot", kind="check_run", status="COMPLETED", conclusion="SUCCESS"),
    ]
    decision = evaluate_auto_merge(
        state="OPEN",
        merged=False,
        is_draft=False,
        mergeable="MERGEABLE",
        body="",
        labels=[],
        checks=checks,
        unresolved_bugbot_threads=2,
        disable_label="automerge:off",
        disable_checkbox_label="Disable default auto-merge for this PR",
        ignored_check_prefixes=(),
        bugbot_check_keywords=("bugbot",),
    )
    assert decision.should_merge is False
    assert "Bugbot has 2 unresolved review thread(s)." in decision.reasons


def test_evaluate_auto_merge_blocks_when_bugbot_check_is_missing() -> None:
    checks = [CheckContext(name="CI / test", kind="check_run", status="COMPLETED", conclusion="SUCCESS")]
    decision = evaluate_auto_merge(
        state="OPEN",
        merged=False,
        is_draft=False,
        mergeable="MERGEABLE",
        body="",
        labels=[],
        checks=checks,
        unresolved_bugbot_threads=0,
        disable_label="automerge:off",
        disable_checkbox_label="Disable default auto-merge for this PR",
        ignored_check_prefixes=(),
        bugbot_check_keywords=("bugbot",),
    )
    assert decision.should_merge is False
    assert "Waiting for a bugbot check run to appear." in decision.reasons


def test_evaluate_auto_merge_ignores_its_own_check_prefix() -> None:
    checks = [
        CheckContext(name="Auto Merge / auto-merge-controller", kind="check_run", status="COMPLETED", conclusion="FAILURE"),
        CheckContext(name="CI / test", kind="check_run", status="COMPLETED", conclusion="SUCCESS"),
        CheckContext(name="bugbot", kind="check_run", status="COMPLETED", conclusion="SUCCESS"),
    ]
    decision = evaluate_auto_merge(
        state="OPEN",
        merged=False,
        is_draft=False,
        mergeable="MERGEABLE",
        body="",
        labels=[],
        checks=checks,
        unresolved_bugbot_threads=0,
        disable_label="automerge:off",
        disable_checkbox_label="Disable default auto-merge for this PR",
        ignored_check_prefixes=("Auto Merge /",),
        bugbot_check_keywords=("bugbot",),
    )
    assert decision.should_merge is True
