"""pytest: repo kökünü sys.path'e ekler, testler `src` paketini import edebilsin."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
