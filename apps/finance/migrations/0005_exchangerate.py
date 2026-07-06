from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0004_revenueshare'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExchangeRate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(db_index=True)),
                ('base_currency', models.CharField(default='EUR', max_length=3)),
                ('currency', models.CharField(
                    choices=[('USD', 'US Dollar'), ('CHF', 'Swiss Franc'), ('EUR', 'Euro')],
                    max_length=3,
                )),
                ('rate', models.DecimalField(
                    decimal_places=6, max_digits=12,
                    help_text='Units of currency per 1 EUR',
                )),
                ('source', models.CharField(default='ECB', max_length=50)),
                ('fetched_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-date', 'currency'],
                'unique_together': {('date', 'base_currency', 'currency')},
            },
        ),
    ]
