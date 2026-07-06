# Hand-written migration: add default billing increment fields to Tariff,
# and fix Rate billing fields (PositiveSmallIntegerField, sane defaults).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rates', '0001_initial'),
    ]

    operations = [
        # Add default billing increment fields to Tariff
        migrations.AddField(
            model_name='tariff',
            name='default_billing_minimum',
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text='Default minimum billed seconds for new rates (e.g. 60 for 60/x billing).',
            ),
        ),
        migrations.AddField(
            model_name='tariff',
            name='default_billing_increment',
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text='Default billing increment in seconds for new rates (e.g. 6 for x/6 billing).',
            ),
        ),
        # Alter Rate.minimum_duration_sec: PositiveIntegerField(default=0) → PositiveSmallIntegerField(default=1)
        migrations.AlterField(
            model_name='rate',
            name='minimum_duration_sec',
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text='Minimum billed seconds (e.g. 60 for 60/x billing).',
            ),
        ),
        # Alter Rate.billing_increment_sec: PositiveIntegerField(default=60) → PositiveSmallIntegerField(default=1)
        migrations.AlterField(
            model_name='rate',
            name='billing_increment_sec',
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text='Billing step in seconds after the minimum (e.g. 6 for x/6 billing).',
            ),
        ),
    ]
