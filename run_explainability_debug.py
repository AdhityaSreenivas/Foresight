import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
django.setup()

import logging
logging.basicConfig(level=logging.DEBUG)

from ml_engine.model_inference import get_active_predictor
predictor = get_active_predictor()
record = {"description": "A serious incident where a worker almost fell.", "department": "Operations"}
out = predictor.predict(record)
print("Top factors:", out.top_factors)
