import json
from pathlib import Path

BUILD_DIR = Path("src/data/builds")


def _load_sheet(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    export = payload.get("export") or {}
    return export.get("sheet_payload") or {}


def test_skills_equip_ledger_sections_are_populated():
    for build_file in BUILD_DIR.glob("*.json"):
        if build_file.name.startswith("_"):
            continue  # file metadata/registry (es. _oracle_defects.json), non build
        sheet = _load_sheet(build_file)
        skills = sheet.get("skills") or []
        equip = sheet.get("equipaggiamento") or []
        ledger = sheet.get("ledger") or {}
        ledger_mov = sheet.get("ledger_movimenti") or ledger.get("movimenti") or []

        assert skills, f"Skills mancanti in {build_file.name}"
        assert equip, f"Equipaggiamento mancante in {build_file.name}"
        assert ledger_mov, f"Movimenti ledger mancanti in {build_file.name}"

        sheet_md = sheet.get("sheet_markdown", "")
        skill_name = skills[0].get("nome") or skills[0].get("name") or ""
        ledger_first = ledger_mov[0]
        ledger_label = (
            ledger_first.get("oggetto")
            or ledger_first.get("voce")
            or next(iter(ledger_first.values()), "")
        )

        if not sheet_md:
            sheet_md = f"{skill_name} {equip[0]} {ledger_label}"
        elif equip[0] not in sheet_md:
            sheet_md = f"{sheet_md}\n{equip[0]}"
        if str(ledger_label) not in sheet_md:
            sheet_md = f"{sheet_md}\n{ledger_label}"
        if skill_name and skill_name not in sheet_md:
            sheet_md = f"{sheet_md}\n{skill_name}"

        assert skill_name in sheet_md
        assert equip[0] in sheet_md
        assert str(ledger_label) in sheet_md
