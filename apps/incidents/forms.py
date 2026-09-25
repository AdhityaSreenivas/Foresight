"""
PSIF Platform — Incident reporter submission form
"""
from django import forms
from .models import Incident
from .services.submission import process_new_incident_submission


class IncidentReportForm(forms.ModelForm):
    """
    Field reporter submission form for safety events, unsafe conditions, and near-misses.
    Captures report identity, detailed narrative, safety context (energy/controls), and outcome.
    """
    class Meta:
        model = Incident
        fields = [
            # Report identity
            "report_type",
            "incident_date",
            "location",
            "department",
            "job_task",
            "equipment_involved",
            # Narrative
            "description",
            "immediate_cause",
            "witness_statement",
            "corrective_actions",
            # Safety context & energy / controls
            "high_energy_present",
            "energy_type",
            "worker_exposed",
            "direct_control_present",
            "control_type",
            "control_condition",
            # Outcome
            "severity_actual",
            "injury_type",
            "body_part",
        ]
        widgets = {
            "incident_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "report_type": forms.Select(attrs={"class": "form-control"}),
            "location": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Duliajan Rig 12, Wellhead area"}),
            "department": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Drilling, Production, Maintenance"}),
            "job_task": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Pipe tripping, Valve maintenance"}),
            "equipment_involved": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. High pressure manifold, Crane"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Describe what occurred, what was observed, and any immediate hazard..."}),
            "immediate_cause": forms.TextInput(attrs={"class": "form-control", "placeholder": "Immediate actions taken or direct cause observed"}),
            "witness_statement": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Witness accounts or statements, if available"}),
            "corrective_actions": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Suggested or implemented corrective actions"}),
            "high_energy_present": forms.Select(attrs={"class": "form-control"}),
            "energy_type": forms.Select(attrs={"class": "form-control"}),
            "worker_exposed": forms.Select(attrs={"class": "form-control"}),
            "direct_control_present": forms.Select(attrs={"class": "form-control"}),
            "control_type": forms.Select(attrs={"class": "form-control"}),
            "control_condition": forms.Select(attrs={"class": "form-control"}),
            "severity_actual": forms.Select(attrs={"class": "form-control"}),
            "injury_type": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Laceration, Bruise, None"}),
            "body_part": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Left hand, None"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Required core fields
        self.fields["description"].required = True
        self.fields["report_type"].required = True
        self.fields["incident_date"].required = True

        # Defaults for safety context should preserve unknown states
        self.fields["high_energy_present"].initial = Incident.SafetyContextState.UNKNOWN
        self.fields["worker_exposed"].initial = Incident.SafetyContextState.UNKNOWN
        self.fields["direct_control_present"].initial = Incident.SafetyContextState.UNKNOWN
        self.fields["energy_type"].initial = Incident.EnergyType.UNKNOWN
        self.fields["control_type"].initial = Incident.ControlType.UNKNOWN
        self.fields["control_condition"].initial = Incident.ControlCondition.UNKNOWN

    def clean_description(self):
        desc = self.cleaned_data.get("description", "").strip()
        if not desc:
            raise forms.ValidationError("Data quality is insufficient for analysis: Incident narrative is empty.")
        return desc

    def clean(self):
        cleaned_data = super().clean()
        report_type = cleaned_data.get("report_type")
        severity_actual = cleaned_data.get("severity_actual")

        # Conflict check: Near miss cannot record lost time or fatality
        if report_type == Incident.ReportType.NEAR_MISS:
            if severity_actual in (Incident.SeverityActual.LOST_TIME, Incident.SeverityActual.FATALITY):
                raise forms.ValidationError(
                    "Contradiction: A report classified as 'Near Miss' cannot record actual severity as "
                    f"'{severity_actual.replace('_', ' ').title()}'. Please select 'Incident' or adjust the actual severity."
                )

        # Centralized canonical data quality gate
        from apps.incidents.services.data_quality import validate_incident_for_analysis
        gate_result = validate_incident_for_analysis(cleaned_data)
        if not gate_result["accepted"]:
            blocking = gate_result.get("blocking_findings", [])
            err_msg = "Data quality is insufficient for analysis."
            if blocking:
                bullet_points = " " + " ".join(blocking)
                full_msg = f"{err_msg}{bullet_points} Add more incident detail and submit again."
            else:
                full_msg = f"{err_msg} Add more incident detail and submit again."

            if any("narrative" in b.lower() or "description" in b.lower() for b in blocking):
                self.add_error("description", "Data quality is insufficient for analysis: " + "; ".join(b for b in blocking if "narrative" in b.lower() or "description" in b.lower()))
            if any("activity" in b.lower() for b in blocking):
                if "job_task" in self.fields:
                    self.add_error("job_task", "Activity is missing.")

            raise forms.ValidationError(full_msg)

        cleaned_data["_data_quality_result"] = gate_result
        return cleaned_data

    def save(self, commit=True):
        incident = super().save(commit=False)
        incident.raw_row = {"submission_source": "reporter_form"}
        if commit:
            incident.save()
            process_new_incident_submission(incident)
        return incident
