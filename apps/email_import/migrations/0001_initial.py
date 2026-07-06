from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('rates', '0005_wider_prefix_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='VendorEmailRule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Friendly label, e.g. "3U Telecom rates"', max_length=200)),
                ('sender_email', models.EmailField(help_text='Exact sender address to match')),
                ('imap_folder', models.CharField(default='INBOX', help_text='IMAP folder to monitor', max_length=200)),
                ('subject_keyword', models.CharField(blank=True, help_text='Only process emails whose subject contains this (case-insensitive)', max_length=200)),
                ('attachment_pattern', models.CharField(blank=True, help_text='Only process attachments whose filename contains this (case-insensitive)', max_length=200)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('tariff', models.ForeignKey(help_text='Tariff to import rates into', on_delete=django.db.models.deletion.PROTECT, related_name='email_rules', to='rates.tariff')),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='RateImportLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email_from', models.CharField(max_length=300)),
                ('email_subject', models.CharField(blank=True, max_length=500)),
                ('attachment_name', models.CharField(blank=True, max_length=300)),
                ('processed_at', models.DateTimeField(auto_now_add=True)),
                ('status', models.CharField(choices=[('success', 'Success'), ('error', 'Error'), ('skipped', 'Skipped')], max_length=10)),
                ('error_message', models.TextField(blank=True)),
                ('destinations_created', models.PositiveIntegerField(default=0)),
                ('std_rates_created', models.PositiveIntegerField(default=0)),
                ('std_rates_updated', models.PositiveIntegerField(default=0)),
                ('origin_groups_created', models.PositiveIntegerField(default=0)),
                ('origin_rates_created', models.PositiveIntegerField(default=0)),
                ('origin_rates_updated', models.PositiveIntegerField(default=0)),
                ('skipped', models.PositiveIntegerField(default=0)),
                ('rule', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='logs', to='email_import.vendoremailrule')),
            ],
            options={'ordering': ['-processed_at']},
        ),
    ]
