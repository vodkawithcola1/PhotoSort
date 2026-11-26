"""English catalog — merged from per-module files (kept separate to avoid edit conflicts)."""
from app.i18n.en import common, core, services, ui_main, ui_panels, ui_viewer

CATALOG: dict[str, str] = {}
for _m in (common, core, services, ui_main, ui_viewer, ui_panels):
    CATALOG.update(_m.MESSAGES)
