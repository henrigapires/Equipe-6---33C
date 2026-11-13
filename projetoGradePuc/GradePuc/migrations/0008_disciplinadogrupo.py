from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('GradePuc', '0007_carregar_curriculos'),
    ]

    operations = [
        migrations.CreateModel(
            name='DisciplinaDoGrupo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('grupo', models.CharField(max_length=20)),
                ('codigo', models.CharField(max_length=20)),
                ('nome', models.CharField(max_length=200)),
            ],
            options={
                'ordering': ['grupo', 'codigo'],
                'unique_together': {('grupo', 'codigo')},
            },
        ),
    ]
