#!/usr/bin/env bash
set -euo pipefail
shopt -s nullglob

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCHIVE_DIR_NAME="${ARCHIVE_DIR_NAME:-_archive_$(date +%Y_%m_%d)}"
ARCHIVE_DIR="$ROOT/$ARCHIVE_DIR_NAME"

if [ -e "$ARCHIVE_DIR" ]; then
  ARCHIVE_DIR="${ARCHIVE_DIR}_$(date +%H%M%S)"
fi

mkdir -p "$ARCHIVE_DIR"

DRY_RUN="${DRY_RUN:-0}"

move_path() {
  local src="$1"
  if [ ! -e "$src" ]; then
    return 0
  fi

  local rel="${src#$ROOT/}"
  local dest="$ARCHIVE_DIR/$rel"
  local dest_dir
  dest_dir="$(dirname "$dest")"

  if [ "$DRY_RUN" = "1" ]; then
    echo "[DRY RUN] mv \"$src\" \"$dest\""
    return 0
  fi

  mkdir -p "$dest_dir"
  mv "$src" "$dest"
}

echo "Archive root: $ARCHIVE_DIR"
echo "DRY_RUN=${DRY_RUN}"

# 1) Backups and recovery artifacts
BACKUP_PATHS=(
  "app.py.backup"
  "config.py.backup"
  "docker-compose.yml.backup"
  "prices.py.backup"
  "routes/chat_routes.py.bak"
  "templates/index.html.backup"
  "obsidian.py.bak"
  "obsidian_original_backup.py"
  "obsidian_restore_candidate.py"
  "obsidian_recovered.py"
  "obsidian.cpython-311.pyc.backup"
  "chats.sqlite3.bak"
)

for rel in "${BACKUP_PATHS[@]}"; do
  move_path "$ROOT/$rel"
done

# 2) Reports & logs
for f in "$ROOT"/PHASE_2_* "$ROOT"/CONTEXT_AWARENESS_* "$ROOT"/app.log; do
  move_path "$f"
done

# 3) Root-level ad-hoc tests (includes test_webdav.py)
for f in "$ROOT"/test_*.py; do
  move_path "$f"
done

# 4) Root-level ad-hoc scripts/benchmarks
EXPERIMENTAL_SCRIPTS=(
  "benchmark.py"
  "benchmark_models.sh"
  "quick_function_test.sh"
)

for rel in "${EXPERIMENTAL_SCRIPTS[@]}"; do
  move_path "$ROOT/$rel"
done

# 5) Benchmark results directory
move_path "$ROOT/tests/obsidian_tool_benchmark/results"

# 6) Legacy docs (archive for future doc rewrite)
LEGACY_DOCS=(
  "docs-reference"
  "LLM_CODEBASE_ANALYSIS_INSTRUCTIONS.md"
  "ALEXA_INTEGRATION_SNIPPET.md"
  "IMPLEMENTATION_MULTI_USER_CONTEXT.md"
  "MULTI_USER_IMPLEMENTATION_SUMMARY.md"
  "DOCUMENTATION_SYNTHESIS_HANDOFF.md"
  "Refactoring 2025-11-16.md"
  "VOICE_ANALYSIS.txt"
)

for rel in "${LEGACY_DOCS[@]}"; do
  move_path "$ROOT/$rel"
done

# 7) Cache/venv dirs (archive-only)
while IFS= read -r -d '' d; do
  move_path "$d"
done < <(find "$ROOT" -type d \( -name '__pycache__' -o -name '.pytest_cache' -o -name '.venv' \) -print0)

echo "Archive complete."
echo "Note: test_webdav.py was moved; docs referencing it may need updating later."
