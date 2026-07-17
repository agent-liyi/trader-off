"""Unit tests for factor template definitions (FR-0100)."""

import pytest

from trader_off.factor_mining.templates import (
    FACTOR_TEMPLATE_VERSION,
    BoolParam,
    ChoiceParam,
    FactorTemplate,
    IntRangeParam,
    list_templates,
)


class TestListTemplates:
    """Tests for list_templates() — AC-FR0100-01, AC-FR0100-03."""

    # AC-FR0100-01: Template count and categories
    def test_ac_fr0100_01_list_templates_count_and_categories(self):
        """AC-FR0100-01: list_templates() returns >=12 FactorTemplate
        across 4 categories (momentum, volatility, volume, fundamental)."""
        templates = list_templates()

        assert isinstance(templates, list), "Expected list"
        assert len(templates) >= 12, f"Expected >=12 templates, got {len(templates)}"
        assert all(isinstance(t, FactorTemplate) for t in templates), (
            "All items must be FactorTemplate instances"
        )

        categories = {t.category for t in templates}
        expected_categories = {"momentum", "volatility", "volume", "fundamental"}
        assert categories == expected_categories, (
            f"Expected categories {expected_categories}, got {categories}"
        )

    # AC-FR0100-01: Template fields integrity
    def test_ac_fr0100_01_template_fields_integrity(self):
        """AC-FR0100-01: Each FactorTemplate has name, category, fields, params, formula."""
        templates = list_templates()

        for t in templates:
            assert isinstance(t.name, str) and t.name, f"Template {t} has empty name"
            assert t.category in {"momentum", "volatility", "volume", "fundamental"}, (
                f"Invalid category: {t.category}"
            )
            assert isinstance(t.fields, list) and len(t.fields) > 0, (
                f"Template {t.name} has empty fields"
            )
            assert all(isinstance(f, str) for f in t.fields), f"Template {t.name} has non-str field"
            assert isinstance(t.params, dict), f"Template {t.name} params is not dict"
            assert isinstance(t.formula, str) and t.formula, f"Template {t.name} has empty formula"

    # AC-FR0100-01: Each category has at least 3 templates
    def test_ac_fr0100_01_min_templates_per_category(self):
        """AC-FR0100-01: Each category must have >=3 templates."""
        templates = list_templates()

        for cat in ("momentum", "volatility", "volume", "fundamental"):
            cat_count = sum(1 for t in templates if t.category == cat)
            assert cat_count >= 3, f"Category '{cat}' has only {cat_count} templates, expected >=3"

    # AC-FR0100-02: IntRangeParam for momentum_N
    def test_ac_fr0100_02_momentum_n_int_range_param(self):
        """AC-FR0100-02: momentum_N template has params['N'] as IntRangeParam
        with min=5, max=60, step=5, expanded() returns 12 values."""
        templates = list_templates()
        momentum_template = next((t for t in templates if t.name == "momentum_N"), None)
        assert momentum_template is not None, "momentum_N template not found"

        n_param = momentum_template.params.get("N")
        assert n_param is not None, "No 'N' param in momentum_N"
        assert isinstance(n_param, IntRangeParam), f"Expected IntRangeParam, got {type(n_param)}"
        assert n_param.min == 5, f"Expected min=5, got {n_param.min}"
        assert n_param.max == 60, f"Expected max=60, got {n_param.max}"
        assert n_param.step == 5, f"Expected step=5, got {n_param.step}"

        expected = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60]
        assert n_param.expanded() == expected, f"Expected {expected}, got {n_param.expanded()}"

    # AC-FR0100-03: Fundamental templates have fundamental-only fields
    def test_ac_fr0100_03_fundamental_templates_fields(self):
        """AC-FR0100-03: Fundamental templates have category='fundamental'
        and fields referencing fundamental data columns (pe, pb, roe, etc.).
        This enables FR-0200's enumerate_factors to skip them when
        fundamental data is unavailable."""
        templates = list_templates()
        fundamental_templates = [t for t in templates if t.category == "fundamental"]
        assert len(fundamental_templates) >= 3, (
            f"Expected >=3 fundamental templates, got {len(fundamental_templates)}"
        )

        # Fundamental templates must reference fundamental-only columns
        fundamental_only_fields = {"pe", "pb", "roe", "revenue_growth", "market_cap"}
        for ft in fundamental_templates:
            # At least one field must be a fundamental-only column
            has_fundamental_field = any(f in fundamental_only_fields for f in ft.fields)
            assert has_fundamental_field, (
                f"Fundamental template '{ft.name}' has no fundamental-only fields: {ft.fields}"
            )

    # AC-FR0100-04: Template version constant
    def test_ac_fr0100_04_template_version_constant(self):
        """AC-FR0100-04: FACTOR_TEMPLATE_VERSION = 'v1'."""
        assert FACTOR_TEMPLATE_VERSION == "v1", f"Expected 'v1', got '{FACTOR_TEMPLATE_VERSION}'"


class TestIntRangeParam:
    """Tests for IntRangeParam dataclass."""

    def test_int_range_param_default_step(self):
        """IntRangeParam defaults step to 1."""
        p = IntRangeParam(name="N", min=1, max=3)
        assert p.step == 1
        assert p.expanded() == [1, 2, 3]

    def test_int_range_param_custom_step(self):
        """IntRangeParam with custom step."""
        p = IntRangeParam(name="N", min=10, max=50, step=10)
        assert p.expanded() == [10, 20, 30, 40, 50]

    def test_int_range_param_single_value(self):
        """IntRangeParam where min == max returns single value."""
        p = IntRangeParam(name="N", min=5, max=5, step=1)
        assert p.expanded() == [5]

    def test_int_range_param_uneven_step_includes_max(self):
        """IntRangeParam with uneven step still includes max value."""
        p = IntRangeParam(name="N", min=5, max=60, step=7)
        result = p.expanded()
        # range(5, 61, 7) = [5, 12, 19, 26, 33, 40, 47, 54]
        # fallback appends 60
        assert result[0] == 5
        assert result[-1] == 60
        assert len(result) == len([5, 12, 19, 26, 33, 40, 47, 54]) + 1

    def test_int_range_param_frozen_immutable(self):
        """IntRangeParam is frozen (immutable)."""
        p = IntRangeParam(name="N", min=1, max=10, step=2)
        with pytest.raises(Exception):  # dataclass FrozenInstanceError or similar
            p.min = 100  # type: ignore[misc]


class TestChoiceParam:
    """Tests for ChoiceParam dataclass."""

    def test_choice_param_creation(self):
        """ChoiceParam stores name and choices."""
        p = ChoiceParam(name="field", choices=["close", "open", "high"])
        assert p.name == "field"
        assert p.choices == ["close", "open", "high"]

    def test_choice_param_frozen_immutable(self):
        """ChoiceParam is frozen (immutable)."""
        p = ChoiceParam(name="method", choices=["pearson", "spearman"])
        with pytest.raises(Exception):
            p.name = "other"  # type: ignore[misc]


class TestBoolParam:
    """Tests for BoolParam dataclass."""

    def test_bool_param_expanded(self):
        """BoolParam.expanded() returns [False, True]."""
        p = BoolParam(name="use_adj_close")
        assert p.expanded() == [False, True]

    def test_bool_param_frozen_immutable(self):
        """BoolParam is frozen (immutable)."""
        p = BoolParam(name="use_adj")
        with pytest.raises(Exception):
            p.name = "other"  # type: ignore[misc]
