from rest_framework import serializers
from .models import ModelVersion

class PredictRequestSerializer(serializers.Serializer):
    """
    Validates canonical fields for a manual prediction request.
    Fields match the core canonical attributes of an Incident.
    """
    description = serializers.CharField(required=True, allow_blank=False, allow_null=False)
    corrective_actions = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    witness_statement = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    
    incident_date = serializers.DateField(required=False, allow_null=True)
    department = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    location = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    job_task = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    equipment_involved = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    
    injury_type = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    body_part = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    immediate_cause = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    root_cause_category = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    
    severity_actual = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    severity_potential = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    near_miss = serializers.BooleanField(required=False, allow_null=True)

class ModelVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModelVersion
        fields = [
            'id', 'version_label', 'is_active', 'status', 'trained_at', 
            'training_snapshot_path', 'metrics'
        ]
