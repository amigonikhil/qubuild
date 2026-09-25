"""Run the whole test suite: python run_tests.py"""
import subprocess
import sys

FILES = ["tests/test_physics.py", "tests/test_backends.py", "tests/test_tutor.py",
         "tests/test_llm.py"]

failed = 0
for path in FILES:
    print("\n" + "=" * 62 + "\n" + path + "\n" + "=" * 62)
    failed |= subprocess.call([sys.executable, path])
sys.exit(1 if failed else 0)
