#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

echo "== line endings =="
# convert any CRLF that Windows editors may have written
find "$ROOT" -type f \( -name '*.py' -o -name '*.sh' -o -name '*.md' -o -name '*.txt' -o -name '*.spec' -o -name '*.desktop' -o -name '.gitignore' -o -name '.gitattributes' -o -name 'LICENSE' \) -print0 \
  | xargs -0 sed -i 's/\r$//'
chmod +x "$ROOT/build.sh" "$ROOT/run.sh" "$ROOT/install.sh" "$ROOT/uninstall.sh" "$ROOT/scripts/linux_verify.sh" "$ROOT/sm0l.py"

bad=0
while IFS= read -r -d '' f; do
  if grep -q $'\r' "$f"; then
    echo "CRLF leftover: $f"
    bad=1
  fi
done < <(find "$ROOT" -type f \( -name '*.py' -o -name '*.sh' -o -name '*.md' \) -print0)
if [[ "$bad" -ne 0 ]]; then
  echo "FAIL: CRLF remains"
  exit 1
fi
echo "ok LF"

echo "== python =="
python3 -m compileall -q src sm0l.py scripts
python3 scripts/smoke.py
python3 scripts/_test_p2p3.py

echo "== paths =="
python3 - <<'PY'
from pathlib import Path
import os, tempfile
td = tempfile.mkdtemp(prefix="sm0l_path_")
os.environ["XDG_CONFIG_HOME"] = str(Path(td) / "cfg")
os.environ["XDG_DATA_HOME"] = str(Path(td) / "data")
from src.paths import config_path, user_data, share_dirs, default_workspace
cfg = config_path()
data = user_data()
assert cfg == Path(td) / "cfg" / "sm0l" / "config.json", cfg
assert data == Path(td) / "data" / "sm0l", data
assert (data / "sessions").is_dir()
assert default_workspace().name == "sm0l_workspace"
print("share_dirs:", [str(p) for p in share_dirs()[:3]])
print("ok paths")
PY

echo "ALL VERIFY OK"
