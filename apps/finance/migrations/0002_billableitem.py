from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_company_payment_terms'),
        ('finance', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='BillableItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('description', models.CharField(max_length=500, help_text='Item name as it appears on the invoice')),
                ('billing_type', models.CharField(
                    max_length=15,
                    choices=[
                        ('one_time',    'One-time'),
                        ('monthly',     'Monthly'),
                        ('quarterly',   'Quarterly (3-monthly)'),
                        ('half_yearly', 'Half-yearly (6-monthly)'),
                        ('yearly',      'Yearly'),
                    ],
                    default='monthly',
                )),
                ('unit_price', models.DecimalField(max_digits=14, decimal_places=4)),
                ('quantity', models.DecimalField(max_digits=10, decimal_places=4, default=1)),
                ('currency', models.CharField(max_length=3, default='USD')),
                ('is_active', models.BooleanField(default=True)),
                ('service_start', models.DateField(null=True, blank=True, help_text='Date service began')),
                ('next_billing_date', models.DateField(null=True, blank=True, help_text='Next auto-invoice date (recurring only)')),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('customer', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='billable_items',
                    to='core.company',
                )),
            ],
            options={
                'ordering': ['-is_active', 'description'],
            },
        ),
    ]
