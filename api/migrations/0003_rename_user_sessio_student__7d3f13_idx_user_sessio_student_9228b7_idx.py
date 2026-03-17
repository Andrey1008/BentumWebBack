
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0002_user_sessions"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="usersession",
            new_name="user_sessio_student_9228b7_idx",
            old_name="user_sessio_student__7d3f13_idx",
        ),
    ]
