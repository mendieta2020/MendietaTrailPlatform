# Generated for PR-134: OrgOAuthCredential — org-scoped MP OAuth token store.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0083_coach_pricing_plan_athlete_subscription'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrgOAuthCredential',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('provider', models.CharField(db_index=True, max_length=40)),
                ('provider_user_id', models.CharField(
                    blank=True,
                    default='',
                    help_text="Provider's account/user ID (e.g., MP user_id).",
                    max_length=120,
                )),
                ('access_token', models.TextField()),
                ('refresh_token', models.TextField(blank=True, default='')),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True)),
                ('organization', models.ForeignKey(
                    db_index=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='org_oauth_credentials',
                    to='core.organization',
                )),
            ],
            options={
                'verbose_name': 'Org OAuth Credential',
                'verbose_name_plural': 'Org OAuth Credentials',
            },
        ),
        migrations.AddConstraint(
            model_name='orgoauthcredential',
            constraint=models.UniqueConstraint(
                fields=['organization', 'provider'],
                name='uniq_org_oauth_cred_org_provider',
            ),
        ),
        migrations.AddIndex(
            model_name='orgoauthcredential',
            index=models.Index(
                fields=['organization', 'provider'],
                name='core_orgoa_organiz_provider_idx',
            ),
        ),
    ]
