from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rates', '0004_origin_based_rating'),
    ]

    operations = [
        migrations.AlterField(
            model_name='rate',
            name='prefix',
            field=models.CharField(max_length=30),
        ),
        migrations.AlterField(
            model_name='origindialcode',
            name='prefix',
            field=models.CharField(help_text='ANI prefix, e.g. 1417', max_length=30),
        ),
    ]
