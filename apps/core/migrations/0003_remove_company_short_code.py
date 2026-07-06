from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_switch_api_token'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='company',
            name='short_code',
        ),
    ]
