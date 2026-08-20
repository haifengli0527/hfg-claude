#!/usr/bin/env python3
import pathlib
import sys
import unittest


if __name__ == "__main__":
    root = pathlib.Path(__file__).resolve().parents[1]
    suite = unittest.defaultTestLoader.discover(str(root / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
