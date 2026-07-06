from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
        ('ddi', '0002_ddinum_customer_nullable'),
    ]

    operations = [
        migrations.AddField(
            model_name='ddinumber',
            name='country',
            field=models.CharField(db_index=True, default='Switzerland', max_length=100),
        ),
        migrations.AddField(
            model_name='ddinumber',
            name='vendor',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='ddi_numbers_as_vendor',
                help_text='Provider/carrier who supplies this number to Lightup.',
                to='core.company',
            ),
        ),
    ]
