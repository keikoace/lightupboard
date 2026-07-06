from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_remove_company_short_code'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='company',
            name='payment_terms_days',
        ),
        migrations.AddField(
            model_name='company',
            name='payment_terms',
            field=models.CharField(
                blank=True,
                default='',
                max_length=10,
                choices=[
                    ('', '— None —'),
                    ('PrePay', 'PrePay'),
                    ('7/3', '7/3  (10 days)'),
                    ('7/7', '7/7  (14 days)'),
                    ('15/3', '15/3  (18 days)'),
                    ('15/5', '15/5  (20 days)'),
                    ('15/7', '15/7  (22 days)'),
                    ('7/15', '7/15  (22 days)'),
                    ('15/15', '15/15  (30 days)'),
                    ('30/7', '30/7  (37 days)'),
                    ('30/10', '30/10  (40 days)'),
                    ('30/15', '30/15  (45 days)'),
                    ('30/30', '30/30  (60 days)'),
                    ('30/60', '30/60  (90 days)'),
                ],
                help_text='Billing period / payment due days (e.g. 30/7 = invoice monthly, due in 7 days)',
            ),
        ),
    ]
