import os, sys
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
import django
django.setup()
from ml_engine.model_inference import get_active_predictor

predictor = get_active_predictor()
if predictor:
    rec1 = {
        'description': 'A worker fell down the stairs and broke his leg', 
        'severity_actual': 'first_aid', 
        'severity_potential': 'low', 
        'department': None
    }
    rec2 = {
        'description': 'Another narrative here completely different text about explosion', 
        'severity_actual': 'fatality', 
        'severity_potential': 'fatality', 
        'department': None
    }
    rec3 = {
        'description': 'Another narrative here completely different text about explosion', 
        'severity_actual': 'first_aid', 
        'severity_potential': 'low', 
        'department': None
    }
    print(predictor.predict(rec1).psif_probability)
    print(predictor.predict(rec2).psif_probability)
    print(predictor.predict(rec3).psif_probability)
