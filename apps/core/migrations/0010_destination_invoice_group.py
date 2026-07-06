from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_trunk'),
    ]

    operations = [
        migrations.AddField(
            model_name='destination',
            name='invoice_group',
            field=models.CharField(
                blank=True,
                max_length=100,
                help_text='Invoice line label e.g. "Germany Fixed". Destinations sharing a group are merged into one invoice line.',
            ),
        ),
    ]
