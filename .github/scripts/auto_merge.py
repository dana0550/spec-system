#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from specctl.automerge_policy import CheckContext, evaluate_auto_merge, parse_csv

GRAPHQL_QUERY = """
query AutoMergePullRequest($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      number
      state
      merged
      isDraft
      mergeable
      body
      labels(first: 100) {
        nodes {
          name
        }
      }
      reviewThreads(first: 100) {
        nodes {
          isResolved
          comments(first: 50) {
            nodes {
              author {
                login
              }
            }
          }
        }
      }
      commits(last: 1) {
        nodes {
          commit {
            statusCheckRollup {
              contexts(first: 100) {
                nodes {
                  __typename
                  ... on CheckRun {
                    name
                    status
                    conclusion
                    app {
                      slug
                      name
                    }
                  }
                  ... on StatusContext {
                    context
                    state
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""


@dataclass(frozen=True)
class Config:
    disable_label: str
    disable_checkbox: str
    ignored_check_prefixes: tuple[str, ...]
    bugbot_check_keywords: tuple[str, ...]
    bugbot_logins: tuple[str, ...]
    merge_method: str


class GitHubClient:
    def __init__(self, token: str, repository: str) -> None:
        owner, name = repository.split("/", 1)
        self.owner = owner
        self.name = name
        self._token = token

    def graphql(self, query: str, variables: dict[str, object]) -> dict[str, object]:
        payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
        request = urllib.request.Request(
            "https://api.github.com/graphql",
            data=payload,
            headers=self._headers(),
            method="POST",
        )
        return _read_json(request)

    def merge_pull_request(self, number: int, method: str) -> tuple[bool, str]:
        request = urllib.request.Request(
            f"https://api.github.com/repos/{self.owner}/{self.name}/pulls/{number}/merge",
            data=json.dumps({"merge_method": method}).encode("utf-8"),
            headers=self._headers(),
            method="PUT",
        )
        try:
            response = _read_json(request)
            merged = bool(response.get("merged"))
            message = str(response.get("message", ""))
            return merged, message
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            return False, f"merge API returned HTTP {exc.code}: {detail}"

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "docs-spec-system-auto-merge",
        }


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    event_path = os.environ.get("GITHUB_EVENT_PATH", "").strip()

    if not token or not repository:
        print("Missing required environment: GITHUB_TOKEN or GITHUB_REPOSITORY.", file=sys.stderr)
        return 1
    if not event_path:
        print("Missing required environment: GITHUB_EVENT_PATH.", file=sys.stderr)
        return 1

    config = Config(
        disable_label=os.environ.get("AUTO_MERGE_DISABLE_LABEL", "automerge:off"),
        disable_checkbox=os.environ.get(
            "AUTO_MERGE_DISABLE_CHECKBOX", "Disable default auto-merge for this PR"
        ),
        ignored_check_prefixes=parse_csv(os.environ.get("AUTO_MERGE_IGNORE_CHECK_PREFIXES", "Auto Merge /")),
        bugbot_check_keywords=parse_csv(os.environ.get("AUTO_MERGE_BUGBOT_CHECK_KEYWORDS", "bugbot,cursor")),
        bugbot_logins=tuple(
            login.lower()
            for login in parse_csv(
                os.environ.get(
                    "AUTO_MERGE_BUGBOT_LOGINS", "cursor[bot],cursor-agent[bot],bugbot[bot]"
                )
            )
        ),
        merge_method=os.environ.get("AUTO_MERGE_METHOD", "merge"),
    )

    event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    pr_numbers = sorted(_extract_pr_numbers(event))
    if not pr_numbers:
        print("No pull request numbers found for this event; nothing to do.")
        return 0

    client = GitHubClient(token=token, repository=repository)
    for pr_number in pr_numbers:
        _evaluate_and_merge(client=client, config=config, pr_number=pr_number)
    return 0


def _extract_pr_numbers(event: dict[str, object]) -> set[int]:
    numbers: set[int] = set()

    pull_request = event.get("pull_request")
    if isinstance(pull_request, dict):
        number = pull_request.get("number")
        if isinstance(number, int):
            numbers.add(number)

    check_run = event.get("check_run")
    if isinstance(check_run, dict):
        prs = check_run.get("pull_requests")
        if isinstance(prs, list):
            for pr in prs:
                if isinstance(pr, dict) and isinstance(pr.get("number"), int):
                    numbers.add(pr["number"])

    check_suite = event.get("check_suite")
    if isinstance(check_suite, dict):
        prs = check_suite.get("pull_requests")
        if isinstance(prs, list):
            for pr in prs:
                if isinstance(pr, dict) and isinstance(pr.get("number"), int):
                    numbers.add(pr["number"])

    return numbers


def _evaluate_and_merge(*, client: GitHubClient, config: Config, pr_number: int) -> None:
    response = client.graphql(
        GRAPHQL_QUERY,
        {"owner": client.owner, "name": client.name, "number": pr_number},
    )
    _assert_graphql_ok(response)
    pr = _read_path(response, "data", "repository", "pullRequest")
    if not isinstance(pr, dict):
        print(f"PR #{pr_number}: not found; skipping.")
        return

    labels = _extract_labels(pr)
    checks = _extract_checks(pr)
    unresolved_bugbot_threads = _count_unresolved_bugbot_threads(pr=pr, bugbot_logins=config.bugbot_logins)

    decision = evaluate_auto_merge(
        state=str(pr.get("state", "")),
        merged=bool(pr.get("merged")),
        is_draft=bool(pr.get("isDraft")),
        mergeable=_string_or_none(pr.get("mergeable")),
        body=str(pr.get("body") or ""),
        labels=labels,
        checks=checks,
        unresolved_bugbot_threads=unresolved_bugbot_threads,
        disable_label=config.disable_label,
        disable_checkbox_label=config.disable_checkbox,
        ignored_check_prefixes=config.ignored_check_prefixes,
        bugbot_check_keywords=config.bugbot_check_keywords,
    )

    if decision.disabled_reason:
        print(f"PR #{pr_number}: auto-merge disabled ({decision.disabled_reason})")
        return

    if not decision.should_merge:
        reasons = "; ".join(decision.reasons)
        print(f"PR #{pr_number}: merge blocked ({reasons})")
        return

    merged, message = client.merge_pull_request(number=pr_number, method=config.merge_method)
    if merged:
        print(f"PR #{pr_number}: merged successfully with method `{config.merge_method}`.")
    else:
        print(f"PR #{pr_number}: merge attempt skipped ({message}).")


def _extract_labels(pr: dict[str, object]) -> list[str]:
    labels: list[str] = []
    label_nodes = _read_path(pr, "labels", "nodes")
    if not isinstance(label_nodes, list):
        return labels
    for node in label_nodes:
        if isinstance(node, dict) and isinstance(node.get("name"), str):
            labels.append(node["name"])
    return labels


def _extract_checks(pr: dict[str, object]) -> list[CheckContext]:
    checks: list[CheckContext] = []
    nodes = _read_path(pr, "commits", "nodes")
    if not isinstance(nodes, list) or not nodes:
        return checks
    contexts = _read_path(nodes[-1], "commit", "statusCheckRollup", "contexts", "nodes")
    if not isinstance(contexts, list):
        return checks
    for context in contexts:
        if not isinstance(context, dict):
            continue
        typename = context.get("__typename")
        if typename == "CheckRun":
            app = context.get("app")
            app_slug = None
            app_name = None
            if isinstance(app, dict):
                if isinstance(app.get("slug"), str):
                    app_slug = app["slug"]
                if isinstance(app.get("name"), str):
                    app_name = app["name"]
            checks.append(
                CheckContext(
                    name=str(context.get("name") or ""),
                    kind="check_run",
                    status=str(context.get("status") or ""),
                    conclusion=_string_or_none(context.get("conclusion")),
                    app_slug=app_slug,
                    app_name=app_name,
                )
            )
        elif typename == "StatusContext":
            checks.append(
                CheckContext(
                    name=str(context.get("context") or ""),
                    kind="status_context",
                    status=str(context.get("state") or ""),
                )
            )
    return checks


def _count_unresolved_bugbot_threads(*, pr: dict[str, object], bugbot_logins: tuple[str, ...]) -> int:
    if not bugbot_logins:
        return 0
    nodes = _read_path(pr, "reviewThreads", "nodes")
    if not isinstance(nodes, list):
        return 0

    unresolved = 0
    for thread in nodes:
        if not isinstance(thread, dict):
            continue
        if bool(thread.get("isResolved")):
            continue
        comments = _read_path(thread, "comments", "nodes")
        if not isinstance(comments, list):
            continue
        authors = {
            author["login"].lower()
            for comment in comments
            if isinstance(comment, dict)
            for author in [comment.get("author")]
            if isinstance(author, dict) and isinstance(author.get("login"), str)
        }
        if authors.intersection(bugbot_logins):
            unresolved += 1
    return unresolved


def _assert_graphql_ok(response: dict[str, object]) -> None:
    errors = response.get("errors")
    if not errors:
        return
    raise RuntimeError(f"GraphQL query failed: {json.dumps(errors, sort_keys=True)}")


def _read_json(request: urllib.request.Request) -> dict[str, object]:
    with urllib.request.urlopen(request) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def _read_path(source: object, *path: str) -> object:
    current = source
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
