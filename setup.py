"""Setup entry point — registers the build_py cmdclass.

The bulk of project configuration lives in ``pyproject.toml``. This shim
exists only to make the custom ``build_py`` (defined in
:mod:`build_helpers`) importable during isolated PEP 517 wheel builds.

With ``[tool.setuptools.cmdclass]`` in ``pyproject.toml`` alone, the
cmdclass module is imported during ``get_requires_for_build_wheel``,
before the project directory is guaranteed on ``sys.path`` — which fails
with ``ModuleNotFoundError``. A ``setup.py`` is executed in-place by
setuptools, so the local import resolves reliably.
"""

from __future__ import annotations

import sys
from pathlib import Path

# In isolated PEP 517 builds the project root is NOT on sys.path, so the
# local build_helpers import below would fail with ModuleNotFoundError.
# setup.py is exec'd in-place, so __file__ resolves to the project root.
_PROJECT_ROOT = str(Path(__file__).resolve().parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from setuptools import setup  # noqa: E402

from build_helpers import build_py  # noqa: E402

setup(
    cmdclass={"build_py": build_py},
)
