from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_company_portal_users'),
    ]

    operations = [
        migrations.AlterField(
            model_name='destination',
            name='prefix',
            field=models.CharField(max_length=30),
        ),
    ]
