from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_company_payment_terms'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='customer_number',
            field=models.PositiveIntegerField(
                null=True, blank=True, unique=True,
                help_text='Sequential customer ID shown on invoices (e.g. 301753)',
            ),
        ),
        migrations.AddField(
            model_name='company',
            name='vat_exempt',
            field=models.BooleanField(
                default=False,
                help_text='If checked, VAT is set to 0% on all invoices for this company',
            ),
        ),
    ]
