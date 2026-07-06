from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_company_account_managers'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='portal_users',
            field=models.ManyToManyField(
                blank=True,
                help_text="Users who can log into the customer portal and view this company's data",
                related_name='customer_companies',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
