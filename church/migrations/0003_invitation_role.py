import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("church", "0002_subscriptionplan_invitation_as_owner_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="invitation",
            name="role",
            field=models.CharField(
                choices=[
                    ("admin", "Admin"),
                    ("pastor", "Pastor"),
                    ("hod", "Head of Department"),
                    ("worker", "Worker"),
                    ("volunteer", "Volunteer"),
                ],
                default="worker",
                max_length=20,
            ),
        ),
    ]
