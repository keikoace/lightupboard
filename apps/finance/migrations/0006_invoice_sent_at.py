from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0005_exchangerate'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
