"""Permite ejecutar los scripts sin instalar el paquete (agrega ``src`` al path).

Lo recomendado es instalar el proyecto con ``pip install -e ".[dev]"``; este
archivo solo hace que ``python scripts/<script>.py`` funcione también sin eso.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    import contrataciones  # noqa: F401
except ModuleNotFoundError:
    sys.path.insert(0, str(ROOT / "src"))
