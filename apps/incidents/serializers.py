from rest_framework import serializers
from django.utils import timezone
from apps.incidents.models import Incident
from apps.predictions.models import PredictionResult


class PredictionResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = PredictionResult
        fields = [
            'psif_probability',
            'psif_predicted',
            'risk_level',
            'top_factors',
            'model_version',
            'created_at',
        ]


class IncidentListSerializer(serializers.ModelSerializer):
    prediction = PredictionResultSerializer(read_only=True)
    dataset_id = serializers.UUIDField(source='dataset.id', read_only=True, default=None)
    dataset_name = serializers.CharField(source='dataset.name', read_only=True, default=None)
    
    class Meta:
        model = Incident
        fields = [
            'id',
            'incident_date',
            'department',
            'severity_actual',
            'severity_potential',
            'is_synthetic',
            'psif_label_source',
            'is_psif_human_label',
            'composite_narrative',
            'prediction',
            'dataset_id',
            'dataset_name',
        ]


class IncidentDetailSerializer(serializers.ModelSerializer):
    prediction = PredictionResultSerializer(read_only=True)
    normalized_entities = serializers.SerializerMethodField()
    
    class Meta:
        model = Incident
        fields = '__all__'

    def get_normalized_entities(self, obj):
        from apps.incidents.services.normalization import normalize_incident_entities
        entities = normalize_incident_entities(obj)
        return {k: v.to_dict() for k, v in entities.items()}


class HumanReviewSerializer(serializers.Serializer):
    """
    Validates a human reviewer's PSIF classification decision.

    Supports both:
    - 3-state human domain decision: 'PSIF', 'NOT_PSIF', 'INSUFFICIENT_INFORMATION'
    - Backward-compatible boolean: is_psif_human_label (True = PSIF, False = NOT_PSIF)

    Also captures optional rubric_answers and was_blinded flag.
    The serializer does NOT mutate the Incident — the view handles that.
    """
    decision = serializers.ChoiceField(
        choices=["PSIF", "NOT_PSIF", "INSUFFICIENT_INFORMATION"],
        required=False,
        default=None,
    )
    is_psif_human_label = serializers.BooleanField(
        required=False,
        default=None,
        allow_null=True,
    )
    rationale = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=4000,
    )
    evidence_notes = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=5000,
    )
    rubric_answers = serializers.JSONField(
        required=False,
        default=dict,
    )
    structured_evidence = serializers.JSONField(
        required=False,
        default=dict,
    )
    was_blinded = serializers.BooleanField(
        required=False,
        default=True,
    )
    previous_decision = serializers.ChoiceField(
        choices=["PSIF", "NOT_PSIF", "INSUFFICIENT_INFORMATION"],
        required=False,
        allow_null=True,
        default=None,
    )
    review_provenance = serializers.CharField(
        required=False,
        default="HUMAN_EXPERT",
        max_length=50,
    )

    def validate(self, data):
        """
        Enforce:
        1. Either 'decision' or 'is_psif_human_label' must be supplied.
        2. Rationale required when overriding heuristic classification or marking insufficient info.
        """
        decision = data.get("decision")
        human_label = data.get("is_psif_human_label")

        # Normalize decision and human_label
        if decision:
            if decision == "PSIF":
                data["is_psif_human_label"] = True
            elif decision == "NOT_PSIF":
                data["is_psif_human_label"] = False
            elif decision == "INSUFFICIENT_INFORMATION":
                data["is_psif_human_label"] = None
        elif human_label is not None:
            data["decision"] = "PSIF" if human_label else "NOT_PSIF"
        else:
            raise serializers.ValidationError({
                "decision": "Either 'decision' ('PSIF', 'NOT_PSIF', 'INSUFFICIENT_INFORMATION') or 'is_psif_human_label' must be provided."
            })

        decision = data.get("decision")
        if "rationale" in self.initial_data:
            rat_str = str(self.initial_data.get("rationale") or "").strip()
            if not rat_str or len(rat_str) < 10:
                raise serializers.ValidationError({
                    "rationale": "A meaningful rationale (at least 10 characters) explaining the adjudication decision is required."
                })
            data["rationale"] = rat_str
        elif decision == "INSUFFICIENT_INFORMATION":
            raise serializers.ValidationError({
                "rationale": "A rationale explaining the missing or ambiguous information is required for 'INSUFFICIENT_INFORMATION'."
            })

        # Merge structured_evidence into rubric_answers if present
        if data.get("structured_evidence"):
            rubric = data.get("rubric_answers") or {}
            rubric.update(data["structured_evidence"])
            data["rubric_answers"] = rubric

        return data


class IncidentReportSubmissionSerializer(serializers.ModelSerializer):
    """
    Serializer for field-reported safety observations and incidents with energy/control context.
    """
    class Meta:
        model = Incident
        fields = [
            "id",
            "report_type",
            "incident_date",
            "location",
            "department",
            "job_task",
            "equipment_involved",
            "description",
            "immediate_cause",
            "witness_statement",
            "corrective_actions",
            "high_energy_present",
            "energy_type",
            "worker_exposed",
            "direct_control_present",
            "control_type",
            "control_condition",
            "control_failed_bypassed",
            "severity_actual",
            "injury_type",
            "body_part",
        ]
        read_only_fields = ["id", "control_failed_bypassed"]
        extra_kwargs = {
            "description": {"required": True},
            "report_type": {"required": True},
            "incident_date": {"required": True},
        }

    def validate_description(self, value):
        if not value or len(value.strip()) < 5:
            raise serializers.ValidationError("Description must be at least 5 characters long.")
        return value.strip()

    def validate(self, data):
        report_type = data.get("report_type")
        severity_actual = data.get("severity_actual")
        if report_type == Incident.ReportType.NEAR_MISS:
            if severity_actual in (Incident.SeverityActual.LOST_TIME, Incident.SeverityActual.FATALITY):
                raise serializers.ValidationError({
                    "severity_actual": "Near miss cannot record lost time or fatality."
                })

        from apps.incidents.services.data_quality import validate_incident_for_analysis
        gate_res = validate_incident_for_analysis(data)
        if not gate_res["accepted"]:
            raise serializers.ValidationError({
                "non_field_errors": ["Data quality is insufficient for analysis."],
                "quality_status": gate_res["quality_status"],
                "blocking_findings": gate_res["blocking_findings"],
                "warning_findings": gate_res["warning_findings"],
                "missing_fields": gate_res["missing_fields"],
            })

        return data

    def create(self, validated_data):
        from .services.submission import process_new_incident_submission
        validated_data["raw_row"] = {"submission_source": "api_submission"}
        incident = super().create(validated_data)
        process_new_incident_submission(incident)
        return incident
