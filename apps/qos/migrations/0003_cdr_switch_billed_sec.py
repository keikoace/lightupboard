from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('qos', '0002_split_billed_duration'),
    ]

    operations = [
        migrations.AddField(
            model_name='cdr',
            name='switch_billed_sec',
            field=models.PositiveIntegerField(
                default=0,
                help_text='Billed seconds as reported by the switch (CSV "Billed Duration" column).',
            ),
        ),
    ]
