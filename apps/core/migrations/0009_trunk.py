from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_destination_wider_prefix'),
        ('rates', '0005_wider_prefix_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='Trunk',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('abbreviation', models.CharField(blank=True, max_length=50)),
                ('prefix', models.CharField(blank=True, help_text='SIP/routing prefix used to identify this trunk on the switch. Leave blank if unused.', max_length=50)),
                ('direction', models.CharField(choices=[('inbound', 'Inbound'), ('outbound', 'Outbound'), ('both', 'Both')], default='both', max_length=10)),
                ('is_active', models.BooleanField(default=True)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='trunks', to='core.company')),
                ('buy_tariff', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='trunks_buying', to='rates.tariff')),
                ('sell_tariff', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='trunks_selling', to='rates.tariff')),
            ],
            options={
                'ordering': ['company', 'name'],
            },
        ),
        migrations.AddConstraint(
            model_name='trunk',
            constraint=models.UniqueConstraint(fields=['company', 'name'], name='unique_trunk_per_company'),
        ),
    ]
