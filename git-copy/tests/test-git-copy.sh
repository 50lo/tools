#!/usr/bin/env bash
#
# Baseline test suite for git-copy.
#
# Usage:
#   ./tests/test-git-copy.sh
#
# Each test runs in a fresh temporary Git repository under an isolated
# temporary HOME, so the developer's repositories and Git configuration
# are never touched. Successful fixtures are removed; failed fixtures
# are preserved and their paths are printed for debugging.
#
# Note: directory-copy tests require rsync. If it is missing, those
# tests are skipped (file-copy tests still run).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GIT_COPY="$PROJECT_ROOT/src/git-copy"

# --- Environment isolation -------------------------------------------------
# Unset inherited Git environment variables so tests cannot be redirected
# into a surrounding repository.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY \
      GIT_COMMON_DIR GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_CONFIG_SYSTEM \
      GIT_CONFIG_GLOBAL GIT_ASKPASS GIT_SSH GIT_SSH_COMMAND \
      GIT_EXEC_PATH GCM_INTERACTIVE

TEST_HOME="$(mktemp -d "${TMPDIR:-/tmp}/git-copy-tests.XXXXXX")"
export HOME="$TEST_HOME"
export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL=/dev/null

cleanup() {
  rm -rf "$TEST_HOME"
}
trap cleanup EXIT

# --- Harness ---------------------------------------------------------------
PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0
FAILED_TESTS=()

CURRENT_TEST=""
TEST_FAILED=false
FIXTURE=""

begin_test() {
  CURRENT_TEST="$1"
  TEST_FAILED=false
}

# Always invoke the script under test, never whatever git-copy is on PATH.
git_copy() {
  "$GIT_COPY" "$@"
}

assert() {
  local desc="$1"; shift
  if "$@"; then
    echo "  ok - $desc"
  else
    echo "  not ok - $desc"
    TEST_FAILED=true
  fi
}

assert_file() {
  local desc="$1" path="$2" expected="$3"
  if [[ -f "$path" && "$(cat "$path" 2>/dev/null)" == "$expected" ]]; then
    echo "  ok - $desc"
  else
    echo "  not ok - $desc"
    TEST_FAILED=true
  fi
}

assert_fails() {
  local desc="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "  not ok - $desc (command unexpectedly succeeded)"
    TEST_FAILED=true
  else
    echo "  ok - $desc"
  fi
}

# Initialise a fixture repository in the given directory and cd into it.
# main: README.md with "main content"
# source: same README.md with "source content", plus a/ and b/ trees
setup_fixture() {
  local dir="$1"
  cd "$dir" || return 1
  git init -q -b main . || return 1
  git config user.name "Test User"
  git config user.email "test@example.com"

  # Compare canonical paths: on macOS mktemp returns /var/... while git
  # reports /private/var/...
  local top
  top="$(git rev-parse --show-toplevel)"
  if [[ "$top" != "$(pwd -P)" ]]; then
    echo "  setup error: fixture not isolated (toplevel: $top)" >&2
    return 1
  fi

  echo "main content" > README.md
  git add README.md
  git commit -qm "main" || return 1

  git checkout -qb source
  echo "source content" > README.md
  mkdir -p a b/nested
  echo "a file" > a/file.txt
  echo "b file" > b/nested/file.txt
  git add -A
  git commit -qm "source" || return 1

  git checkout -q main
}

run_test() {
  local name="$1" fn="$2"
  echo "== $name"
  # The fixture path is created here (not in the subshell) so the parent can
  # report or remove it afterwards.
  FIXTURE="$(mktemp -d "$TEST_HOME/fixture.XXXXXX")"
  if (
    begin_test "$name"
    setup_fixture "$FIXTURE" || exit 1
    "$fn"
    [[ "$TEST_FAILED" == false ]]
  ); then
    PASS_COUNT=$((PASS_COUNT + 1))
    echo "PASS: $name"
    rm -rf "$FIXTURE"
  else
    FAIL_COUNT=$((FAIL_COUNT + 1))
    FAILED_TESTS+=("$name")
    echo "FAIL: $name"
    echo "  fixture preserved at: $FIXTURE"
  fi
  FIXTURE=""
}

# --- Tests -----------------------------------------------------------------

test_file_copy() {
  git_copy source README.md out/README.md
  assert_file "copied file content matches source" out/README.md "source content"
  assert "copied file is untracked in working tree" \
    bash -c 'git status --porcelain -- out/README.md | grep -q "^??"'
}

test_default_destination() {
  # README.md already exists on main, so skip the overwrite prompt.
  git_copy --force source README.md
  assert_file "default destination is the source path" README.md "source content"
}

test_directory_copy() {
  command -v rsync >/dev/null 2>&1 || { echo "  skip - rsync not available"; return 0; }
  git_copy source a
  assert_file "nested file copied" a/file.txt "a file"
  assert "directory is untracked in working tree" \
    bash -c 'git status --porcelain -- a | grep -q "^??"'
}

test_directory_mirror_deletes_extra() {
  command -v rsync >/dev/null 2>&1 || { echo "  skip - rsync not available"; return 0; }
  mkdir -p b/nested
  echo "extra" > b/nested/extra.txt
  git add -A && git commit -qm "add extra"
  git_copy --force source b
  assert_file "source file copied" b/nested/file.txt "b file"
  assert "destination-only file removed (rsync --delete mirror)" \
    bash -c '! [[ -e b/nested/extra.txt ]]'
}

test_rename_file() {
  git_copy source README.md docs/readme.md
  assert_file "file copied to renamed destination" docs/readme.md "source content"
  assert_file "original path untouched" README.md "main content"
}

test_parent_dirs_created() {
  git_copy source README.md deep/nested/dir/README.md
  assert_file "parent directories created automatically" deep/nested/dir/README.md "source content"
}

test_force_overwrite() {
  echo "old" > existing.txt
  git_copy --force source README.md existing.txt
  assert_file "--force overwrites without prompt" existing.txt "source content"
}

test_prompt_declined() {
  echo "old" > existing.txt
  printf 'n\n' | git_copy source README.md existing.txt
  assert_file "declined prompt leaves destination unchanged" existing.txt "old"
}

test_prompt_accepted() {
  echo "old" > existing.txt
  printf 'y\n' | git_copy source README.md existing.txt
  assert_file "accepted prompt overwrites destination" existing.txt "source content"
}

test_paths_with_spaces() {
  git checkout -q source
  mkdir -p "dir with spaces"
  echo "spacey" > "dir with spaces/file.txt"
  git add -A && git commit -qm "spaces"
  git checkout -q main

  git_copy source "dir with spaces/file.txt" "out dir/renamed.txt"
  assert_file "spaces in source and destination paths" "out dir/renamed.txt" "spacey"
}

test_run_from_subdirectory() {
  # Paths are relative to the current directory, not the repo root.
  # b/ exists only on the source branch, so create it on main first.
  mkdir b && cd b
  git_copy source nested/file.txt copy.txt
  assert_file "file copied relative to cwd" copy.txt "b file"
  assert "file not written relative to repo root" bash -c '! [[ -e ../copy.txt ]]'

  command -v rsync >/dev/null 2>&1 || { echo "  skip - rsync not available"; return 0; }
  git_copy source nested out
  assert_file "directory copied relative to cwd" out/file.txt "b file"
}

test_missing_arguments() {
  assert_fails "no arguments fails" git_copy
  assert_fails "one argument fails" git_copy source
  assert_fails "four arguments fail" git_copy source README.md a b
}

test_unknown_option() {
  assert_fails "unknown option fails" git_copy --bogus source README.md
}

test_invalid_branch() {
  assert_fails "nonexistent branch fails" git_copy no-such-branch README.md
}

test_missing_source() {
  assert_fails "path not in branch fails" git_copy source no/such/path.txt
}

test_untracked_source() {
  git checkout -q source
  echo "untracked" > untracked.txt
  git checkout -q main
  assert_fails "uncommitted file in source branch fails" git_copy source untracked.txt
}

test_file_into_directory_conflict() {
  # README.md is a tracked file on main; replace it with a directory.
  rm README.md && mkdir README.md
  assert_fails "copying a file onto a directory fails" git_copy --force source README.md
  assert "directory left in place" bash -c '[[ -d README.md ]]'
}

test_directory_into_file_conflict() {
  command -v rsync >/dev/null 2>&1 || { echo "  skip - rsync not available"; return 0; }
  echo "i am a file" > a
  assert_fails "copying a directory onto a file fails" git_copy --force source a
  assert_file "file left in place" a "i am a file"
}

# --- Main ------------------------------------------------------------------

main() {
  if [[ ! -x "$GIT_COPY" ]]; then
    echo "error: $GIT_COPY not found or not executable" >&2
    exit 1
  fi

  # Directory-copy tests need rsync; report it up front.
  if ! command -v rsync >/dev/null 2>&1; then
    echo "warning: rsync not found - directory-copy tests will be skipped" >&2
  fi

  run_test "copy file from another branch"        test_file_copy
  run_test "default destination is source path"   test_default_destination
  run_test "copy a directory"                     test_directory_copy
  run_test "directory copy mirrors source"        test_directory_mirror_deletes_extra
  run_test "rename a file"                        test_rename_file
  run_test "parent directories are created"       test_parent_dirs_created
  run_test "--force overwrites"                   test_force_overwrite
  run_test "declined prompt aborts copy"          test_prompt_declined
  run_test "accepted prompt overwrites"           test_prompt_accepted
  run_test "paths with spaces"                    test_paths_with_spaces
  run_test "run from a subdirectory"              test_run_from_subdirectory
  run_test "missing arguments fail"               test_missing_arguments
  run_test "unknown option fails"                 test_unknown_option
  run_test "invalid branch fails"                 test_invalid_branch
  run_test "missing source fails"                 test_missing_source
  run_test "untracked source fails"               test_untracked_source
  run_test "file into directory conflict fails"   test_file_into_directory_conflict
  run_test "directory into file conflict fails"   test_directory_into_file_conflict

  echo
  echo "Results: $PASS_COUNT passed, $FAIL_COUNT failed"
  if [[ ${#FAILED_TESTS[@]} -gt 0 ]]; then
    echo "Failed tests:"
    for t in "${FAILED_TESTS[@]}"; do
      echo "  - $t"
    done
  fi
  [[ $FAIL_COUNT -eq 0 ]]
}

main "$@"
