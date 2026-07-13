import sys
from pathlib import Path

# 讓 tests 不需安裝套件即可 import smartdoc
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
