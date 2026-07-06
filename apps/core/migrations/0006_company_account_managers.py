from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_company_customer_number_vat_exempt'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='account_managers',
            field=models.ManyToManyField(
                blank=True,
                help_text='Account managers responsible for this company',
                related_name='managed_companies',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
