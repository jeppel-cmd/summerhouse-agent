from __future__ import annotations

import sys
from pathlib import Path


vendor_local = Path(__file__).resolve().parent / ".vendor_local"
external_site_packages = Path.home() / "AppData" / "Local" / "Programs" / "Python" / "Python314" / "Lib" / "site-packages"
if external_site_packages.exists():
    sys.path.insert(0, str(external_site_packages))
if vendor_local.exists():
    sys.path.insert(0, str(vendor_local))
