from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('rates', '0003_auditlog'),
    ]

    operations = [
        migrations.CreateModel(
            name='OriginGroup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Group code from vendor, e.g. AT-A', max_length=100, unique=True)),
                ('description', models.CharField(blank=True, max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='OriginDialcode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('prefix', models.CharField(help_text='ANI prefix, e.g. 1417', max_length=20)),
                ('effective_date', models.DateField()),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='dialcodes', to='rates.origingroup')),
            ],
            options={'ordering': ['prefix'], 'unique_together': {('group', 'prefix')}},
        ),
        migrations.AddField(
            model_name='rate',
            name='origin_group',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='rates',
                help_text='If set, rate applies only when ANI matches this origin group.',
                to='rates.origingroup',
            ),
        ),
        migrations.AlterUniqueTogether(
            name='rate',
            unique_together={('tariff', 'prefix', 'effective_date', 'origin_group')},
        ),
    ]
