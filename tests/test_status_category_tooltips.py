"""
PSIF Platform — Tests for Dataset Processing Status Data Quality Tooltips

Verifies:
1. Accepted category renders with info icon and popover.
2. Accepted with Warning category renders with info icon and popover.
3. Rejected category renders with info icon and popover.
4. Tooltip/popover text communicates general classification criteria accurately.
5. Popover text contains no row-specific data.
6. Counts remain dynamic.
7. Existing row-level rejection details remain functional and distinct from generic popovers.
8. Accessibility attributes (type="button", aria-label, aria-expanded, aria-controls, role="tooltip").
"""
import pytest
from django.urls import reverse
from rest_framework import status

from apps.datasets.models import Dataset


@pytest.mark.django_db
class TestStatusCategoryTooltips:

    @pytest.fixture
    def sample_dataset(self, safety_user):
        return Dataset.objects.create(
            name="test_dataset_quality.csv",
            uploaded_by=safety_user,
            file_type="csv",
            status=Dataset.Status.COMPLETED,
            total_rows=100,
            processed_rows=100,
            error_rows=5,
            quality_summary={
                "total": 100,
                "accepted": 80,
                "accepted_with_warnings": 15,
                "rejected": 5,
                "rejections": [
                    {"row": 12, "reason": "Incident narrative is empty."},
                    {"row": 45, "reason": "Incident date is in the future."},
                ]
            }
        )

    def test_status_page_renders_all_category_headers_and_icons(self, safety_client, safety_user, sample_dataset):
        safety_client.force_login(safety_user)
        url = reverse("datasets:status", kwargs={"pk": sample_dataset.id})
        response = safety_client.get(url)
        assert response.status_code == status.HTTP_200_OK

        html = response.content.decode("utf-8")

        # 1. Accepted Category & Icon
        assert "Accepted" in html
        assert 'id="btn-info-accepted"' in html
        assert 'aria-label="About accepted records"' in html
        assert 'id="popover-info-accepted"' in html

        # 2. Accepted with Warning Category & Icon
        assert "Accepted with Warning" in html
        assert 'id="btn-info-warnings"' in html
        assert 'aria-label="About records accepted with warnings"' in html
        assert 'id="popover-info-warnings"' in html

        # 3. Rejected Category & Icon
        assert "Rejected" in html
        assert 'id="btn-info-rejected"' in html
        assert 'aria-label="About rejected records"' in html
        assert 'id="popover-info-rejected"' in html

    def test_tooltip_content_accuracy_and_general_classification(self, safety_client, safety_user, sample_dataset):
        safety_client.force_login(safety_user)
        url = reverse("datasets:status", kwargs={"pk": sample_dataset.id})
        response = safety_client.get(url)
        html = response.content.decode("utf-8")

        # Accepted explanation
        assert "These records contain sufficient information for automated safety analysis" in html
        assert "coherent enough to proceed with PSIF analysis" in html

        # Accepted with warning explanation
        assert "These records contain enough information to be analyzed, but some data-quality limitations may reduce analytical confidence" in html
        assert "These records are still processed for downstream PSIF predictions and explanations" in html

        # Rejected explanation
        assert "These records contain critical data-quality problems that make reliable automated analysis inappropriate" in html
        assert "Rejected records do not receive automated PSIF predictions or SHAP explanations and are not included in model training" in html

    def test_popover_text_does_not_contain_row_specific_data(self, safety_client, safety_user, sample_dataset):
        """Generic category popovers must not contain row numbers or specific IDs."""
        safety_client.force_login(safety_user)
        url = reverse("datasets:status", kwargs={"pk": sample_dataset.id})
        response = safety_client.get(url)
        html = response.content.decode("utf-8")

        # Extract popover blocks
        for popover_id in ["popover-info-accepted", "popover-info-warnings", "popover-info-rejected"]:
            start = html.find(f'id="{popover_id}"')
            assert start != -1
            end = html.find('</div>\n                            </div>', start)
            popover_html = html[start:end]

            # Ensure no row references inside category popovers
            assert "Row 12" not in popover_html
            assert "Row 45" not in popover_html
            assert "row_num" not in popover_html
            assert "external_id" not in popover_html

    def test_dynamic_counts_and_rejections_list_preserved(self, safety_client, safety_user, sample_dataset):
        """Dynamic counts and row-level rejection table remain intact."""
        safety_client.force_login(safety_user)
        url = reverse("datasets:status", kwargs={"pk": sample_dataset.id})
        response = safety_client.get(url)
        html = response.content.decode("utf-8")

        # Dynamic counts are present
        assert 'id="dq-count-accepted">80</td>' in html
        assert 'id="dq-count-warnings">15</td>' in html
        assert 'id="dq-count-rejected">5</td>' in html

        # Rejections list is present and distinct from category popovers
        assert 'id="dq-rejections-container"' in html
        assert "Row 12" in html
        assert "Incident narrative is empty." in html
        assert "Row 45" in html
        assert "Incident date is in the future." in html

    def test_accessibility_semantics(self, safety_client, safety_user, sample_dataset):
        safety_client.force_login(safety_user)
        url = reverse("datasets:status", kwargs={"pk": sample_dataset.id})
        response = safety_client.get(url)
        html = response.content.decode("utf-8")

        # Buttons must have explicit type="button", aria-expanded, aria-controls
        for btn_id, popover_id in [
            ("btn-info-accepted", "popover-info-accepted"),
            ("btn-info-warnings", "popover-info-warnings"),
            ("btn-info-rejected", "popover-info-rejected"),
        ]:
            assert f'id="{btn_id}"' in html
            assert 'type="button"' in html
            assert f'aria-controls="{popover_id}"' in html
            assert 'aria-expanded="false"' in html

        # Popovers must have role="tooltip" and aria-hidden="true"
        for popover_id in ["popover-info-accepted", "popover-info-warnings", "popover-info-rejected"]:
            assert f'id="{popover_id}" role="tooltip" aria-hidden="true"' in html
