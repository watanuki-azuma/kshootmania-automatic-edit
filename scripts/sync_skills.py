"""Copy skills/ into .claude/skills (Claude Code) and .agents/skills (Codex).

Copies instead of symlinks so the repository also works on Windows checkouts.
docs/draft-format.md is copied into each skill that ships a draft-format reference.

Usage: uv run python scripts/sync_skills.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARED = {"references/draft-format.md": ROOT / "docs" / "draft-format.md"}


def main() -> None:
    src = ROOT / "skills"
    for skill in sorted(p for p in src.iterdir() if (p / "SKILL.md").exists()):
        for rel, origin in SHARED.items():
            if (skill / rel).parent.exists():
                shutil.copyfile(origin, skill / rel)
        for target in (ROOT / ".claude" / "skills", ROOT / ".agents" / "skills"):
            dest = target / skill.name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(skill, dest)
            print(f"{skill.name} -> {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
