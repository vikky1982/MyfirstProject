from django.db import migrations, models

import vocabulary.codes


def fill_codes(apps, schema_editor):
    Learner = apps.get_model("vocabulary", "Learner")
    used = set()
    for learner in Learner.objects.all():
        code = vocabulary.codes.new_learner_code()
        while code in used or Learner.objects.filter(code=code).exists():
            code = vocabulary.codes.new_learner_code()
        used.add(code)
        learner.code = code
        learner.save(update_fields=["code"])


class Migration(migrations.Migration):

    dependencies = [
        ("vocabulary", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="learner",
            name="code",
            field=models.CharField(max_length=12, null=True),
        ),
        migrations.RunPython(fill_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="learner",
            name="code",
            field=models.CharField(
                default=vocabulary.codes.new_learner_code,
                max_length=12,
                unique=True,
            ),
        ),
    ]
