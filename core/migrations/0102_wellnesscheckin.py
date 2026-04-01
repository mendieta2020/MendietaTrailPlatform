# PR-154: WellnessCheckIn model + AthleteProfile.wellness_checkin_dismissed

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0101_athleteprofile_last_period_date_athleteinjury'),
    ]

    operations = [
        migrations.AddField(
            model_name='athleteprofile',
            name='wellness_checkin_dismissed',
            field=models.BooleanField(
                default=False,
                help_text='If True, athlete has opted out of daily wellness check-ins permanently.',
            ),
        ),
        migrations.CreateModel(
            name='WellnessCheckIn',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(help_text='Date of the check-in. One per athlete per day.')),
                ('sleep_quality', models.PositiveSmallIntegerField(
                    help_text='Perceived sleep quality: 1=very poor, 5=excellent.',
                    validators=[
                        django.core.validators.MinValueValidator(1),
                        django.core.validators.MaxValueValidator(5),
                    ],
                )),
                ('mood', models.PositiveSmallIntegerField(
                    help_text='Mood/motivation: 1=very low, 5=excellent.',
                    validators=[
                        django.core.validators.MinValueValidator(1),
                        django.core.validators.MaxValueValidator(5),
                    ],
                )),
                ('energy', models.PositiveSmallIntegerField(
                    help_text='Energy level: 1=very low, 5=high.',
                    validators=[
                        django.core.validators.MinValueValidator(1),
                        django.core.validators.MaxValueValidator(5),
                    ],
                )),
                ('muscle_soreness', models.PositiveSmallIntegerField(
                    help_text='Muscle soreness: 1=very sore, 5=no soreness.',
                    validators=[
                        django.core.validators.MinValueValidator(1),
                        django.core.validators.MaxValueValidator(5),
                    ],
                )),
                ('stress', models.PositiveSmallIntegerField(
                    help_text='Perceived stress: 1=very stressed, 5=very relaxed.',
                    validators=[
                        django.core.validators.MinValueValidator(1),
                        django.core.validators.MaxValueValidator(5),
                    ],
                )),
                ('notes', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('athlete', models.ForeignKey(
                    db_index=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='wellness_checkins',
                    to='core.athlete',
                )),
                ('organization', models.ForeignKey(
                    db_index=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='wellness_checkins',
                    to='core.organization',
                )),
            ],
            options={
                'ordering': ['-date'],
            },
        ),
        migrations.AddConstraint(
            model_name='wellnesscheckin',
            constraint=models.UniqueConstraint(
                fields=['athlete', 'date'],
                name='unique_wellness_athlete_date',
            ),
        ),
        migrations.AddIndex(
            model_name='wellnesscheckin',
            index=models.Index(fields=['organization', 'athlete', 'date'], name='core_wellne_organiz_idx'),
        ),
    ]
