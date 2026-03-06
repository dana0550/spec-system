#!/usr/bin/env bash
set -euo pipefail

# Poll PR Bugbot status and unresolved Bugbot review threads.
# If unresolved Bugbot threads exist, this worker can invoke Codex to address them.
#
# Usage:
#   scripts/bugbot_poll_worker.sh [PR_NUMBER]
#
# Environment:
#   INTERVAL_SECONDS   Poll interval in seconds (default: 300)
#   AUTO_ADDRESS       1 to auto-run Codex on unresolved Bugbot threads (default: 1)
#   LOG_FILE           Log file path (default: <repo>/.tmp/bugbot-poll-worker.log)
#   MAX_CYCLES         Optional maximum poll iterations before exit (default: unlimited)

INTERVAL_SECONDS="${INTERVAL_SECONDS:-300}"
AUTO_ADDRESS="${AUTO_ADDRESS:-1}"
MAX_CYCLES="${MAX_CYCLES:-0}"

REPO_ROOT="$(git rev-parse --show-toplevel)"
PR_NUMBER="${1:-}"
if [[ -z "${PR_NUMBER}" ]]; then
  PR_NUMBER="$(gh pr view --json number --jq '.number')"
fi

NAME_WITH_OWNER="$(gh repo view --json nameWithOwner --jq '.nameWithOwner')"
OWNER="${NAME_WITH_OWNER%%/*}"
REPO="${NAME_WITH_OWNER##*/}"

LOG_FILE="${LOG_FILE:-$REPO_ROOT/.tmp/bugbot-poll-worker.log}"
mkdir -p "$(dirname "$LOG_FILE")"

timestamp() {
  date +"%Y-%m-%d %H:%M:%S %Z"
}

log() {
  local msg="$1"
  echo "[$(timestamp)] $msg" | tee -a "$LOG_FILE"
}

check_dependencies() {
  command -v gh >/dev/null 2>&1 || {
    log "ERROR: gh CLI is required"
    exit 1
  }
  command -v jq >/dev/null 2>&1 || {
    log "ERROR: jq is required"
    exit 1
  }
  command -v codex >/dev/null 2>&1 || {
    log "ERROR: codex CLI is required"
    exit 1
  }
}

get_head_sha() {
  gh pr view "$PR_NUMBER" --json headRefOid --jq '.headRefOid'
}

get_bugbot_state_json() {
  local head_sha="$1"
  gh api "repos/$OWNER/$REPO/commits/$head_sha/check-runs" \
    --jq '[.check_runs[] | select(.app.slug=="cursor" and .name=="Cursor Bugbot")] | sort_by(.id) | last // {"id":0,"status":"missing","conclusion":""}'
}

get_unresolved_bugbot_threads() {
  gh api graphql \
    -F owner="$OWNER" \
    -F repo="$REPO" \
    -F number="$PR_NUMBER" \
    -f query='query($owner:String!, $repo:String!, $number:Int!) {
      repository(owner:$owner, name:$repo) {
        pullRequest(number:$number) {
          reviewThreads(first:100) {
            nodes {
              isResolved
              comments(first:5) {
                nodes {
                  author { login }
                }
              }
            }
          }
        }
      }
    }' \
    --jq '[.data.repository.pullRequest.reviewThreads.nodes[]
      | select(.isResolved==false)
      | select([.comments.nodes[].author.login] | any(.=="cursor"))
    ] | length'
}

run_auto_address() {
  local prompt
  prompt=$(
    cat <<'EOF'
Address unresolved PR review comments on the open pull request for the current branch.
Use gh CLI to fetch unresolved threads, apply fixes one by one, run relevant tests, commit, push, and resolve threads.
Stop when unresolved review threads are zero.
EOF
  )
  log "Launching codex auto-address run for unresolved Bugbot threads"
  codex exec \
    -C "$REPO_ROOT" \
    "$prompt" 2>&1 | tee -a "$LOG_FILE" || true
}

check_dependencies
log "Starting Bugbot poll worker on PR #$PR_NUMBER (interval=${INTERVAL_SECONDS}s auto_address=${AUTO_ADDRESS})"

cycle=0
while true; do
  cycle=$((cycle + 1))
  head_sha="$(get_head_sha)"
  bugbot_json="$(get_bugbot_state_json "$head_sha")"
  bugbot_id="$(jq -r '.id' <<<"$bugbot_json")"
  bugbot_status="$(jq -r '.status' <<<"$bugbot_json")"
  bugbot_conclusion="$(jq -r '.conclusion // ""' <<<"$bugbot_json")"
  unresolved_threads="$(get_unresolved_bugbot_threads)"

  log "Cycle $cycle: sha=$head_sha bugbot_id=$bugbot_id status=$bugbot_status conclusion=${bugbot_conclusion:-none} unresolved_bugbot_threads=$unresolved_threads"

  if [[ "$unresolved_threads" -eq 0 ]] \
    && [[ "$bugbot_status" == "completed" ]] \
    && [[ "$bugbot_conclusion" != "failure" ]] \
    && [[ "$bugbot_conclusion" != "timed_out" ]] \
    && [[ "$bugbot_conclusion" != "cancelled" ]] \
    && [[ "$bugbot_conclusion" != "action_required" ]]; then
    log "Bugbot completed cleanly with no unresolved Bugbot threads. Exiting worker."
    break
  fi

  if [[ "$unresolved_threads" -gt 0 ]] && [[ "$AUTO_ADDRESS" == "1" ]]; then
    run_auto_address
  fi

  if [[ "$MAX_CYCLES" -gt 0 ]] && [[ "$cycle" -ge "$MAX_CYCLES" ]]; then
    log "Reached MAX_CYCLES=$MAX_CYCLES. Exiting worker."
    break
  fi

  sleep "$INTERVAL_SECONDS"
done
