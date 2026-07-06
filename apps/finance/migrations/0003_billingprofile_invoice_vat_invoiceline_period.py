from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0002_billableitem'),
        ('core', '0005_company_customer_number_vat_exempt'),
    ]

    operations = [
        # ── Create BillingProfile ─────────────────────────────────────────────
        migrations.CreateModel(
            name='BillingProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name',         models.CharField(max_length=100)),
                ('short_code',   models.CharField(max_length=20, unique=True)),
                ('currency',     models.CharField(max_length=3, default='USD')),
                ('company_name', models.CharField(max_length=200, default='Lightup Network Solutions GmbH & Co. KG')),
                ('address_line1',models.CharField(max_length=200, default='Hinterbergstr. 24')),
                ('address_line2',models.CharField(max_length=200, default='6312 Steinhausen')),
                ('country',      models.CharField(max_length=100, default='Schweiz')),
                ('phone',        models.CharField(max_length=50, blank=True, default='+49 (0)69 962 4456 0')),
                ('fax',          models.CharField(max_length=50, blank=True, default='+49 (0)69 962 4456 20')),
                ('email',        models.EmailField(blank=True, default='info@lightupnet.de')),
                ('website',      models.CharField(max_length=200, blank=True, default='http://www.lightupnet.de')),
                ('ceo',          models.CharField(max_length=100, blank=True, default='Markus Stalder')),
                ('vat_id',       models.CharField(max_length=50, blank=True)),
                ('chamber',      models.CharField(max_length=100, blank=True)),
                ('iban',         models.CharField(max_length=50, blank=True)),
                ('bic',          models.CharField(max_length=20, blank=True)),
                ('bank_name',    models.CharField(max_length=100, blank=True)),
                ('vat_rate',     models.DecimalField(max_digits=5, decimal_places=2, default=0)),
                ('next_invoice_number', models.PositiveIntegerField(default=1)),
                ('is_active',    models.BooleanField(default=True)),
            ],
            options={'ordering': ['name']},
        ),

        # ── Add billing_profile + vat_rate to Invoice ─────────────────────────
        migrations.AddField(
            model_name='invoice',
            name='billing_profile',
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='invoices',
                to='finance.billingprofile',
            ),
        ),
        migrations.AddField(
            model_name='invoice',
            name='vat_rate',
            field=models.DecimalField(max_digits=5, decimal_places=2, default=0),
        ),

        # ── Update InvoiceLine ────────────────────────────────────────────────
        migrations.AddField(
            model_name='invoiceline',
            name='sort_order',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='invoiceline',
            name='quantity',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='invoiceline',
            name='title',
            field=models.CharField(max_length=200, default='Call Termination'),
        ),
        migrations.AddField(
            model_name='invoiceline',
            name='period_start',
            field=models.DateField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='invoiceline',
            name='period_end',
            field=models.DateField(null=True, blank=True),
        ),
        # Change description to TextField (was CharField max_length=300)
        migrations.AlterField(
            model_name='invoiceline',
            name='description',
            field=models.TextField(blank=True),
        ),
        # Increase minutes precision to 3 decimal places
        migrations.AlterField(
            model_name='invoiceline',
            name='minutes',
            field=models.DecimalField(max_digits=14, decimal_places=3, default=0),
        ),
    ]
