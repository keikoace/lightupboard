# Hand-written migration: replace billed_duration_sec with
# buy_billed_duration_sec and sell_billed_duration_sec on CDR.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('qos', '0001_initial'),
    ]

    operations = [
        # Add the two new fields (both default to 0 so existing rows are fine).
        migrations.AddField(
            model_name='cdr',
            name='buy_billed_duration_sec',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='cdr',
            name='sell_billed_duration_sec',
            field=models.PositiveIntegerField(default=0),
        ),
        # Copy existing billed_duration_sec into both new fields so data is
        # not silently zeroed for CDRs processed before this migration.
        migrations.RunSQL(
            sql='''
                UPDATE qos_cdr
                SET buy_billed_duration_sec  = billed_duration_sec,
                    sell_billed_duration_sec = billed_duration_sec
                WHERE billed_duration_sec > 0;
            ''',
            reverse_sql=migrations.RunSQL.noop,
        ),
        # Drop the old column.
        migrations.RemoveField(
            model_name='cdr',
            name='billed_duration_sec',
        ),
    ]
