from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_company_account_managers'),
        ('finance', '0003_billingprofile_invoice_vat_invoiceline_period'),
    ]

    operations = [
        migrations.CreateModel(
            name='RevenueShare',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('description', models.CharField(max_length=300, blank=True)),
                ('share_pct', models.DecimalField(max_digits=6, decimal_places=3)),
                ('start_date', models.DateField(null=True, blank=True)),
                ('end_date', models.DateField(null=True, blank=True)),
                ('is_active', models.BooleanField(default=True)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='revenue_shares',
                    to='core.company',
                )),
            ],
            options={'ordering': ['-is_active', 'company__name']},
        ),
    ]
