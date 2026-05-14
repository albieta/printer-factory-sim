"""Entry point: python -m engine"""

import sys
from engine.turn_engine import main

sys.exit(main(sys.argv[1:]))
