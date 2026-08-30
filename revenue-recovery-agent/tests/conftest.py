import os
import sys

# Tests live in revenue-recovery-agent/tests/ but import the pipeline modules
# from revenue-recovery-agent/, which pytest does not put on sys.path by default.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
