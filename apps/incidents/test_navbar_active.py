from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


class NavbarActiveStateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="safety_officer",
            password="testpassword123",
            role=User.Role.SAFETY_OFFICER,
        )
        self.client.login(username="safety_officer", password="testpassword123")

    def test_submit_report_highlights_nav_report_not_incidents(self):
        """
        Verify that /incidents/report/ activates 'nav_report' and NOT 'nav_incidents'.
        Regression test for Phase 14 / Bug D.
        """
        url = reverse("incidents:report")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")

        # Must have class="sidebar-link active" on the Submit Report link
        self.assertIn('href="/incidents/report/" class="sidebar-link active"', content)

        # Must NOT have class="sidebar-link active" on the Incidents link
        self.assertNotIn('href="/incidents/" class="sidebar-link active"', content)

    def test_incidents_list_highlights_nav_incidents(self):
        """
        Verify that /incidents/ activates 'nav_incidents' and NOT 'nav_report'.
        """
        url = reverse("incidents:list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")

        self.assertIn('href="/incidents/" class="sidebar-link active"', content)
        self.assertNotIn('href="/incidents/report/" class="sidebar-link active"', content)
