from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_alter_homepage_hero_background'),
    ]

    operations = [
        migrations.AddField(
            model_name='sitesettings',
            name='max_url',
            field=models.URLField(blank=True, verbose_name='Ссылка на Max'),
        ),
    ]
