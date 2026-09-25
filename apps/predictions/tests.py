from django.test import TestCase
import uuid
from apps.incidents.models import Incident
from apps.predictions.iogp_classifier import classify_iogp_rules
from apps.dashboard.pattern_detection import detect_recurring_patterns, detect_multi_site_recurrence
from apps.incidents.models import IOGPRuleTag

class IOGPClassifierTests(TestCase):
    def test_classifier_matches_confined_space(self):
        incident = Incident.objects.create(
            id=uuid.uuid4(),
            composite_narrative="Worker entered the confined space without a permit to enter.",
            job_task="Vessel Maintenance",
            department="Maintenance",
            incident_date="2026-09-01"
        )
        fields = {
            "composite_narrative": incident.composite_narrative,
            "job_task": incident.job_task
        }
        matches = classify_iogp_rules(fields)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['rule'], "Confined Space")
        self.assertIn("confined space", matches[0]['matched_keywords'])
        self.assertIn("permit to enter", matches[0]['matched_keywords'])
        self.assertEqual(matches[0]['match_strength'], 1.0)
        self.assertEqual(matches[0]['match_type'], "direct_event")
        self.assertEqual(matches[0]['classifier_version'], "iogp_rules_v2")

    def test_direct_positive_match(self):
        fields = {
            "description": "Worker performed tank entry without permit and experienced dizziness.",
            "job_task": "Tank cleaning"
        }
        matches = classify_iogp_rules(fields)
        self.assertTrue(any(m['rule'] == "Confined Space" for m in matches))
        match = next(m for m in matches if m['rule'] == "Confined Space")
        self.assertEqual(match['match_strength'], 1.0)
        self.assertEqual(match['match_type'], "direct_event")

    def test_negated_matches_rejected(self):
        # Spec §34: "No confined space entry occurred." must not match Confined Space
        fields_cs1 = {"description": "No confined space entry occurred during the inspection."}
        self.assertEqual(len(classify_iogp_rules(fields_cs1)), 0)

        fields_cs2 = {"description": "Worker completed hatch inspection without entering confined space."}
        self.assertEqual(len(classify_iogp_rules(fields_cs2)), 0)

        # Spec §34: "No lifting operation was performed." must not be interpreted as actual lifting
        fields_lift1 = {"description": "No lifting operation was performed."}
        self.assertEqual(len(classify_iogp_rules(fields_lift1)), 0)

        fields_lift2 = {"description": "Pipes were manually shifted; lifting operation was not carried out."}
        self.assertEqual(len(classify_iogp_rules(fields_lift2)), 0)

        # "Not a line of fire event"
        fields_lof = {"description": "Technician tripped over low curb; not a line of fire event."}
        self.assertEqual(len(classify_iogp_rules(fields_lof)), 0)

        # "No hot work was conducted"
        fields_hw = {"description": "Cold cutting performed; no hot work was conducted."}
        self.assertEqual(len(classify_iogp_rules(fields_hw)), 0)

    def test_incidental_mention(self):
        # Spec §35: "The welding machine was stored nearby." does not prove Hot Work occurred
        fields = {"description": "Worker bumped elbow on doorway. The welding machine was stored nearby."}
        matches = classify_iogp_rules(fields)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['rule'], "Hot Work")
        self.assertEqual(matches[0]['match_type'], "incidental")
        self.assertEqual(matches[0]['match_strength'], 0.3)
        self.assertEqual(matches[0]['confidence'], 0.3)

    def test_corrective_action_mention(self):
        # Spec §35: "Risk assessment was revised after the incident." does not prove Work Authorization failure
        fields_narrative = {"description": "Worker pinched finger. Risk assessment was revised after the incident."}
        matches = classify_iogp_rules(fields_narrative)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['rule'], "Work Authorization")
        self.assertEqual(matches[0]['match_type'], "corrective_action")
        self.assertEqual(matches[0]['match_strength'], 0.5)

        # Mention only in corrective_actions field
        fields_ca = {
            "description": "Minor water leak from valve bonnet.",
            "corrective_actions": "Conduct toolbox talk and review permit to work requirements with crew."
        }
        matches_ca = classify_iogp_rules(fields_ca)
        self.assertEqual(len(matches_ca), 1)
        self.assertEqual(matches_ca[0]['rule'], "Work Authorization")
        self.assertEqual(matches_ca[0]['match_type'], "corrective_action")
        self.assertEqual(matches_ca[0]['match_strength'], 0.5)

    def test_multiple_rule_match(self):
        fields = {
            "description": "Worker on scaffolding fell 4 meters while performing welding without safety harness.",
            "job_task": "Hot work at height"
        }
        matches = classify_iogp_rules(fields)
        rules = {m['rule'] for m in matches}
        self.assertIn("Working at Height", rules)
        self.assertIn("Hot Work", rules)

    def test_classifier_no_match(self):
        incident = Incident.objects.create(
            id=uuid.uuid4(),
            composite_narrative="Worker slipped on water in the break room.",
            job_task="Break",
            department="Admin",
            incident_date="2026-09-01"
        )
        fields = {
            "composite_narrative": incident.composite_narrative,
            "job_task": incident.job_task
        }
        matches = classify_iogp_rules(fields)
        self.assertEqual(len(matches), 0)

    def test_all_nine_rules_available(self):
        canonical_prompts = {
            "Bypassing Safety Controls": "Technician bypassed the safety control interlock on the pump.",
            "Confined Space": "Operator performed vessel entry for cleaning.",
            "Driving": "Driver was speeding and lost control of the vehicle.",
            "Energy Isolation": "Electrician opened breaker without LOTO lockout isolation.",
            "Hot Work": "Welder ignited torch for cutting pipe.",
            "Line of Fire": "Helper stood in the line of fire and was struck by dropped object.",
            "Safe Mechanical Lifting": "Crane operator lifted suspended load over working area.",
            "Work Authorization": "Team proceeded without a valid permit to work.",
            "Working at Height": "Scaffolder worked at height on scaffold without harness."
        }
        for expected_rule, prompt in canonical_prompts.items():
            matches = classify_iogp_rules({"description": prompt})
            matched_rule_names = [m["rule"] for m in matches]
            self.assertIn(
                expected_rule,
                matched_rule_names,
                f"Rule '{expected_rule}' failed to match canonical prompt: {prompt}"
            )

class PatternDetectionTests(TestCase):
    def setUp(self):
        # Create some incidents and tags
        i1 = Incident.objects.create(
            id=uuid.uuid4(), composite_narrative="driving fast", job_task="Driving", department="Logistics", incident_date="2026-09-01"
        )
        i2 = Incident.objects.create(
            id=uuid.uuid4(), composite_narrative="speeding", job_task="Driving", department="Logistics", incident_date="2026-09-02"
        )
        i3 = Incident.objects.create(
            id=uuid.uuid4(), composite_narrative="fatigue driving", job_task="Driving", department="Sales", incident_date="2026-09-03"
        )
        i4 = Incident.objects.create(
            id=uuid.uuid4(), composite_narrative="seat belt issue", job_task="Driving", department="Admin", incident_date="2026-09-04"
        )
        
        IOGPRuleTag.objects.create(incident=i1, rule="Driving", classification_method="keyword_stemming", confidence=1.0, matched_keywords=["driving"], matched_fields=["composite_narrative"])
        IOGPRuleTag.objects.create(incident=i2, rule="Driving", classification_method="keyword_stemming", confidence=1.0, matched_keywords=["speeding"], matched_fields=["composite_narrative"])
        IOGPRuleTag.objects.create(incident=i3, rule="Driving", classification_method="keyword_stemming", confidence=1.0, matched_keywords=["fatigue driving"], matched_fields=["composite_narrative"])
        IOGPRuleTag.objects.create(incident=i4, rule="Driving", classification_method="keyword_stemming", confidence=1.0, matched_keywords=["seat belt"], matched_fields=["composite_narrative"])
        
    def test_recurring_patterns(self):
        patterns = detect_recurring_patterns(min_occurrences=2)
        # Should find Driving/Logistics (count = 2)
        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0]['site'], "Logistics")
        self.assertEqual(patterns[0]['activity'], "Driving")
        self.assertEqual(patterns[0]['occurrence_count'], 2)
        self.assertEqual(patterns[0]['rule'], "Driving")

    def test_multi_site_recurrence(self):
        alerts = detect_multi_site_recurrence(min_sites=2)
        # Should find Driving across Logistics, Sales, Admin
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['rule'], "Driving")
        self.assertEqual(alerts[0]['site_count'], 3)
        self.assertEqual(alerts[0]['total_incidents'], 4)
        self.assertIn("Logistics", alerts[0]['sites'])
        self.assertIn("Sales", alerts[0]['sites'])
        self.assertIn("Admin", alerts[0]['sites'])
