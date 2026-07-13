from __future__ import annotations

from PyInstaller.utils.hooks import check_requirement, collect_submodules

datas = []
excludedimports = ["sqlalchemy.testing"]
hiddenimports = [
    "sqlalchemy.ext.baked",
    *collect_submodules("sqlalchemy.dialects.sqlite"),
]

if check_requirement("sqlalchemy >= 1.4"):
    hiddenimports.append("sqlalchemy.sql.default_comparator")
