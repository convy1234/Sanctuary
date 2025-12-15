from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("church", "0003_invitation_role"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="organizationsubscription",
            name="seat_limit",
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="capacity_min",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="capacity_max",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
