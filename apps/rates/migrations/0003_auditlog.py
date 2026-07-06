from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('rates', '0002_billing_increments'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('object_type', models.CharField(max_length=20)),
                ('object_id', models.PositiveIntegerField()),
                ('object_repr', models.CharField(max_length=300)),
                ('action', models.CharField(
                    choices=[('create', 'Created'), ('update', 'Updated'), ('delete', 'Deleted')],
                    max_length=10,
                )),
                ('user', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('before_json', models.TextField(blank=True)),
                ('after_json', models.TextField(blank=True)),
            ],
            options={'ordering': ['-timestamp']},
        ),
    ]
