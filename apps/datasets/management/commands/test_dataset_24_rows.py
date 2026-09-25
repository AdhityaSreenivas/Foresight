from django.core.management.base import BaseCommand
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.datasets.models import Dataset
from apps.datasets.tasks import process_dataset
from apps.datasets.parsers import parse_preview
from django.contrib.auth import get_user_model

class Command(BaseCommand):
    help = 'Test 24 row processing'

    def handle(self, *args, **kwargs):
        User = get_user_model()
        admin, _ = User.objects.get_or_create(username="testadmin2")

        csv_content = b"description,department,severity_actual\n"
        for i in range(24):
            # The last row does not have a newline
            if i == 23:
                csv_content += f"desc {i},dept {i},none".encode()
            else:
                csv_content += f"desc {i},dept {i},none\n".encode()

        file = SimpleUploadedFile("test_24_rows.csv", csv_content, content_type="text/csv")
        dataset = Dataset.objects.create(name="test_24_rows", uploaded_by=admin, file_type="csv", status=Dataset.Status.MAPPING_PENDING)
        dataset.original_file = file
        dataset.save()

        preview = parse_preview(dataset.original_file.path, "csv")
        dataset.total_rows = preview.total_rows
        dataset.column_mapping = {"description": "description", "department": "department", "severity_actual": "severity_actual"}
        dataset.status = Dataset.Status.PROCESSING
        dataset.save()

        print("Estimated Total Rows:", dataset.total_rows)

        result = process_dataset(str(dataset.id))
        dataset.refresh_from_db()

        print("Result:", result)
        print("Final Database State:")
        print(f"Processed Rows: {dataset.processed_rows}")
        print(f"Total Rows: {dataset.total_rows}")
        print(f"Error Rows: {dataset.error_rows}")
        print(f"Status: {dataset.status}")
        print(f"Percent Complete: {dataset.percent_complete}")
