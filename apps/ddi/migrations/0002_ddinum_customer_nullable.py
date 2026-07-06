from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
        ('ddi', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ddinumber',
            name='customer',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='ddi_numbers',
                to='core.company',
            ),
        ),
    ]
