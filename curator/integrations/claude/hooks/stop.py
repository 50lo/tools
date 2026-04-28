import runpy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "hooks"))
runpy.run_path(str(ROOT / "hooks" / "stop.py"), run_name="__main__")
