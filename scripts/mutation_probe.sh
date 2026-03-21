#!/usr/bin/env bash
# Mutation probe: break the implementation in targeted ways, verify
# tests catch each break. A test suite that stays green under mutation
# is a test suite that isn't testing anything.
#
# Judges one thing: did pytest exit non-zero? Greppin g for "passed" in
# the output is wrong — "2 passed, 1 failed" still contains "passed".
set -uo pipefail

export CONVERSATION_REPO_TEST_DSN="${CONVERSATION_REPO_TEST_DSN:-postgresql://testuser:testpass@localhost:54329/testdb}"

REPO="src/database/conversation_repository.py"
ROUTE="src/api/routes/conversations.py"
HIST="src/api/routes/history.py"

survived=0
caught=0

probe() {
  local name="$1" file="$2" pattern="$3" replacement="$4" test_target="$5"
  cp "$file" "$file.orig"
  # -E: extended regex not needed, we want literal match. Escape $ for sed.
  if ! sed -i '' "s|${pattern}|${replacement}|" "$file"; then
    echo "  ! $name — sed failed"
    mv "$file.orig" "$file"
    return
  fi
  # Sanity: did the mutation actually change the file?
  if diff -q "$file" "$file.orig" >/dev/null; then
    echo "  ! $name — mutation had no effect (pattern not found)"
    mv "$file.orig" "$file"
    return
  fi
  if uv run pytest "$test_target" -x -q --tb=line -p no:cacheprovider >/dev/null 2>&1; then
    echo "  ✗ $name — SURVIVED"
    survived=$((survived + 1))
  else
    echo "  ✓ $name — caught"
    caught=$((caught + 1))
  fi
  mv "$file.orig" "$file"
}

echo "── repository mutations ──"
probe "drop tenant filter from get_messages ownership check" \
  "$REPO" \
  "WHERE id = \$1 AND customer_id = \$2\"," \
  "WHERE id = \$1\"," \
  "tests/integration/test_conversation_repository.py::TestTenantIsolation::test_wrong_customer_sees_none"

probe "drop tenant filter from append_message guard" \
  "$REPO" \
  "WHERE id = \$1 AND customer_id = \$4" \
  "WHERE id = \$1 OR \$4 = \$4" \
  "tests/integration/test_conversation_repository.py::TestTenantIsolation::test_wrong_customer_cannot_append"

probe "drop ORDER BY from get_messages" \
  "$REPO" \
  "ORDER BY timestamp, id" \
  "/\* no order \*/" \
  "tests/integration/test_conversation_repository.py::TestAppendMessage::test_order_by_is_load_bearing"

probe "drop customer filter from list_conversations" \
  "$REPO" \
  "WHERE customer_id = \$1 " \
  "WHERE \$1 = \$1 " \
  "tests/integration/test_conversation_repository.py::TestListConversations::test_list_returns_customers_conversations_only"

probe "drop updated_at bump on append" \
  "$REPO" \
  "UPDATE conversations SET updated_at = now()" \
  "SELECT 1 /\* no bump \*/" \
  "tests/integration/test_conversation_repository.py::TestAppendMessage::test_append_bumps_conversation_updated_at"

probe "overwrite ownership on conflict" \
  "$REPO" \
  "ON CONFLICT (id) DO NOTHING" \
  "ON CONFLICT (id) DO UPDATE SET customer_id = EXCLUDED.customer_id" \
  "tests/integration/test_conversation_repository.py::TestTenantIsolation::test_same_conversation_id_different_customers_cannot_collide"

probe "drop CASCADE behaviour check" \
  "$REPO" \
  "DELETE FROM conversations WHERE customer_id = \$1" \
  "DELETE FROM conversations WHERE customer_id = \$1 AND false" \
  "tests/integration/test_conversation_repository.py::TestDeleteCustomerData::test_delete_removes_conversations_and_messages"

echo "── route mutations ──"
probe "persist with wrong role names (LangChain 'human')" \
  "$ROUTE" \
  'role="user",' \
  'role="human",' \
  "tests/unit/api/test_conversations.py::TestPersistence::test_persistence_uses_canonical_role_names"

probe "skip persistence entirely" \
  "$ROUTE" \
  "if repo is not None:" \
  "if repo is not None and False:" \
  "tests/unit/api/test_conversations.py::TestPersistence::test_post_creates_conversation_and_appends_two_messages"

probe "history bypasses repo" \
  "$HIST" \
  "history = await repo.get_messages(" \
  "history = []  # await repo.get_messages(" \
  "tests/unit/api/test_history.py::TestTenantIsolation::test_repo_called_with_token_customer_id"

echo
echo "── result: ${caught} caught, ${survived} survived ──"
exit $survived
