import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='switch',
            name='api_token',
            field=models.UUIDField(
                default=uuid.uuid4,
                unique=True,
                editable=False,
                help_text='Secret token used by this switch to authenticate CDR API posts.',
            ),
        ),
    ]
