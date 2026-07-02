"""Early-career / New Grad classification and Discord routing tests."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.discord_push import _get_category
from scripts.ingestion.role_filter import is_early_career, matches_target_role


class TestEarlyCareerClassification:
    def test_new_grad_suffix_title(self):
        cats = matches_target_role("Software Engineer, New Grad")
        assert "New Grad" in cats
        assert cats[0] == "New Grad"  # priority order: New Grad routes the channel

    def test_new_grad_prefix_title(self):
        cats = matches_target_role("2026 New Grad - Backend Engineer")
        assert "New Grad" in cats

    def test_junior_modifier(self):
        cats = matches_target_role("Junior Software Engineer")
        assert "New Grad" in cats
        assert "SWE" in cats

    def test_intern_modifier(self):
        cats = matches_target_role("Software Engineering Intern")
        assert "New Grad" in cats

    def test_entry_level_modifier(self):
        cats = matches_target_role("Entry Level Data Analyst")
        assert "New Grad" in cats
        assert "Data Analyst" in cats

    def test_class_year_modifier(self):
        cats = matches_target_role("Software Engineer (2026 Start)")
        assert "New Grad" in cats

    def test_engineer_i_modifier(self):
        cats = matches_target_role("Software Engineer I")
        assert "New Grad" in cats

    def test_engineer_ii_not_early_career(self):
        cats = matches_target_role("Software Engineer II")
        assert "New Grad" not in cats

    def test_experience_years_signal(self):
        cats = matches_target_role("Software Engineer", experience_years=1)
        assert "New Grad" in cats

    def test_experience_years_above_threshold(self):
        cats = matches_target_role("Software Engineer", experience_years=5)
        assert "New Grad" not in cats

    def test_seniority_veto(self):
        cats = matches_target_role("Senior Software Engineer", experience_years=2)
        assert "New Grad" not in cats

    def test_modifier_alone_does_not_pass_filter(self):
        # "Intern" without a target-role match must not slip through the filter
        assert matches_target_role("Marketing Intern") == []

    def test_word_boundary_intern(self):
        # "International" / "Internal" must not trigger the intern signal
        assert not is_early_career("International Software Engineer Lead")
        assert "New Grad" not in matches_target_role("Internal Tools Software Engineer")

    def test_standalone_new_grad_passes_filter(self):
        # Explicit new-grad titles count even without a role keyword
        cats = matches_target_role("New Grad Program - Technology")
        assert "New Grad" in cats

    def test_deterministic_order(self):
        a = matches_target_role("Junior Machine Learning Engineer")
        b = matches_target_role("Junior Machine Learning Engineer")
        assert a == b
        assert a[0] == "New Grad"


class TestDiscordCategoryRouting:
    def test_new_grad_wins_regardless_of_stored_order(self):
        assert _get_category({"keywords_matched": ["SWE", "New Grad"]}) == "New Grad"
        assert _get_category({"keywords_matched": ["New Grad", "SWE"]}) == "New Grad"

    def test_json_string_keywords(self):
        assert _get_category({"keywords_matched": '["SWE", "New Grad"]'}) == "New Grad"

    def test_no_keywords(self):
        assert _get_category({"keywords_matched": []}) == "Uncategorized"
