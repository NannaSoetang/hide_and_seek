import sys
from pathlib import Path

from reportlab.platypus import PageBreak


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.pdf import generate_game_guide_pdf as guide


def test_game_guide_contains_only_the_rules_list():
    guide.create_styles()

    story = guide.build_story()
    rendered_text = " ".join(flowable.getPlainText() for flowable in story if hasattr(flowable, "getPlainText"))

    assert guide.TITLE in rendered_text
    assert all(title in rendered_text for title, _bullets in guide.RULES)
    assert not any(isinstance(flowable, PageBreak) for flowable in story)
