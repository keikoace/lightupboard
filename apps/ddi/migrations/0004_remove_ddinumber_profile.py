from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('ddi', '0003_ddinumber_country_vendor'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='ddinumber',
            name='profile',
        ),
    ]
