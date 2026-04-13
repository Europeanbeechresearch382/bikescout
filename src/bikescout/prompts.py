from pathlib import Path

class BikeScoutPrompts:
    def __init__(self):
        self.prompts_dir = Path(__file__).parent / "prompts"
        self.prompts_data = {}
        self._load_all_prompts()

    def _load_all_prompts(self):
        if self.prompts_dir.exists():
            for md_file in self.prompts_dir.glob("*.md"):
                slug = md_file.stem
                self.prompts_data[slug] = md_file.read_text(encoding="utf-8")