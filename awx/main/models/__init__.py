# Copyright (c) 2015 Ansible, Inc.
# All Rights Reserved.

# Django
from django.conf import settings  # noqa
from django.db import connection
from django.db.models.signals import pre_delete  # noqa

# AWX
from awx.main.models.base import BaseModel, PrimordialModel, prevent_search, accepts_json, CLOUD_INVENTORY_SOURCES, VERBOSITY_CHOICES  # noqa
from awx.main.models.unified_jobs import UnifiedJob, UnifiedJobTemplate, StdoutMaxBytesExceeded  # noqa
from awx.main.models.organization import Organization, Profile, Team, UserSessionMembership  # noqa
from awx.main.models.credential import Credential, CredentialType, CredentialInputSource, ManagedCredentialType, build_safe_env  # noqa
from awx.main.models.projects import Project, ProjectUpdate  # noqa
from awx.main.models.inventory import (  # noqa
    CustomInventoryScript,
    Group,
    Host,
    HostMetric,
    Inventory,
    InventorySource,
    InventoryUpdate,
    SmartInventoryMembership,
)
from awx.main.models.jobs import (  # noqa
    Job,
    JobHostSummary,
    JobLaunchConfig,
    JobTemplate,
    SystemJob,
    SystemJobTemplate,
)
from awx.main.models.events import (  # noqa
    AdHocCommandEvent,
    InventoryUpdateEvent,
    JobEvent,
    ProjectUpdateEvent,
    SystemJobEvent,
    UnpartitionedAdHocCommandEvent,
    UnpartitionedInventoryUpdateEvent,
    UnpartitionedJobEvent,
    UnpartitionedProjectUpdateEvent,
    UnpartitionedSystemJobEvent,
)
from awx.main.models.ad_hoc_commands import AdHocCommand  # noqa
from awx.main.models.schedules import Schedule  # noqa
from awx.main.models.execution_environments import ExecutionEnvironment  # noqa
from awx.main.models.activity_stream import ActivityStream  # noqa
from awx.main.models.ha import (  # noqa
    Instance,
    InstanceLink,
    InstanceGroup,
    TowerScheduleState,
)
from awx.main.models.rbac import (  # noqa
    Role,
    batch_role_ancestor_rebuilding,
    get_roles_on_resource,
    role_summary_fields_generator,
    ROLE_SINGLETON_SYSTEM_ADMINISTRATOR,
    ROLE_SINGLETON_SYSTEM_AUDITOR,
)
from awx.main.models.mixins import (  # noqa
    CustomVirtualEnvMixin,
    ExecutionEnvironmentMixin,
    ResourceMixin,
    SurveyJobMixin,
    SurveyJobTemplateMixin,
    TaskManagerInventoryUpdateMixin,
    TaskManagerJobMixin,
    TaskManagerProjectUpdateMixin,
    TaskManagerUnifiedJobMixin,
)
from awx.main.models.notifications import Notification, NotificationTemplate, JobNotificationMixin  # noqa
from awx.main.models.label import Label  # noqa
from awx.main.models.workflow import (  # noqa
    WorkflowJob,
    WorkflowJobNode,
    WorkflowJobOptions,
    WorkflowJobTemplate,
    WorkflowJobTemplateNode,
    WorkflowApproval,
    WorkflowApprovalTemplate,
)
from awx.api.versioning import reverse
from awx.main.models.oauth import OAuth2AccessToken, OAuth2Application  # noqa
from oauth2_provider.models import Grant, RefreshToken  # noqa -- needed django-oauth-toolkit model migrations


# Add custom methods to User model for permissions checks.
from django.contrib.auth.models import User  # noqa
from awx.main.access import get_user_queryset, check_user_access, check_user_access_with_errors, user_accessible_objects  # noqa


User.add_to_class('get_queryset', get_user_queryset)
User.add_to_class('can_access', check_user_access)
User.add_to_class('can_access_with_errors', check_user_access_with_errors)
User.add_to_class('accessible_objects', user_accessible_objects)


def convert_jsonfields_to_jsonb():
    if connection.vendor != 'postgresql':
        return

    # fmt: off
    fields = [  # Table name, expensive or not, tuple of column names
        ('conf_setting', False, (
            'value',
        )),
        ('main_instancegroup', False, (
            'policy_instance_list',
        )),
        ('main_jobtemplate', False, (
            'survey_spec',
        )),
        ('main_notificationtemplate', False, (
            'notification_configuration',
            'messages',
        )),
        ('main_project', False, (
            'playbook_files',
            'inventory_files',
        )),
        ('main_schedule', False, (
            'extra_data',
            'char_prompts',
            'survey_passwords',
        )),
        ('main_workflowjobtemplate', False, (
            'survey_spec',
            'char_prompts',
        )),
        ('main_workflowjobtemplatenode', False, (
            'char_prompts',
            'extra_data',
            'survey_passwords',
        )),
        ('main_activitystream', True, (
            'setting',  # NN = NOT NULL
            'deleted_actor',
        )),
        ('main_job', True, (
            'survey_passwords',  # NN
            'artifacts',  # NN
        )),
        ('main_joblaunchconfig', True, (
            'extra_data',  # NN
            'survey_passwords',  # NN
            'char_prompts',  # NN
        )),
        ('main_notification', True, (
            'body',  # NN
        )),
        ('main_unifiedjob', True, (
            'job_env',  # NN
        )),
        ('main_workflowjob', True, (
            'survey_passwords',  # NN
            'char_prompts',  # NN
        )),
        ('main_workflowjobnode', True, (
            'char_prompts',  # NN
            'ancestor_artifacts',  # NN
            'extra_data',  # NN
            'survey_passwords',  # NN
        )),
    ]
    # fmt: on

    with connection.cursor() as cursor:
        for table, expensive, columns in fields:
            cursor.execute(
                """
                select count(1) from information_schema.columns
                where
                  table_name = %s and
                  column_name in %s and
                  data_type != 'jsonb';
                """,
                (table, columns),
            )
            if cursor.fetchone()[0]:
                from awx.main.tasks.system import migrate_json_fields

                migrate_json_fields.apply_async([table, expensive, columns])


def cleanup_created_modified_by(sender, **kwargs):
    # work around a bug in django-polymorphic that doesn't properly
    # handle cascades for reverse foreign keys on the polymorphic base model
    # https://github.com/django-polymorphic/django-polymorphic/issues/229
    for cls in (UnifiedJobTemplate, UnifiedJob):
        cls.objects.filter(created_by=kwargs['instance']).update(created_by=None)
        cls.objects.filter(modified_by=kwargs['instance']).update(modified_by=None)


pre_delete.connect(cleanup_created_modified_by, sender=User)


@property
def user_get_organizations(user):
    return Organization.objects.filter(member_role__members=user)


@property
def user_get_admin_of_organizations(user):
    return Organization.objects.filter(admin_role__members=user)


@property
def user_get_auditor_of_organizations(user):
    return Organization.objects.filter(auditor_role__members=user)


@property
def created(user):
    return user.date_joined


User.add_to_class('organizations', user_get_organizations)
User.add_to_class('admin_of_organizations', user_get_admin_of_organizations)
User.add_to_class('auditor_of_organizations', user_get_auditor_of_organizations)
User.add_to_class('created', created)


@property
def user_is_system_auditor(user):
    if not hasattr(user, '_is_system_auditor'):
        if user.pk:
            user._is_system_auditor = user.roles.filter(singleton_name='system_auditor', role_field='system_auditor').exists()
        else:
            # Odd case where user is unsaved, this should never be relied on
            return False
    return user._is_system_auditor


@user_is_system_auditor.setter
def user_is_system_auditor(user, tf):
    if not user.id:
        # If the user doesn't have a primary key yet (i.e., this is the *first*
        # time they've logged in, and we've just created the new User in this
        # request), we need one to set up the system auditor role
        user.save()
    if tf:
        role = Role.singleton('system_auditor')
        # must check if member to not duplicate activity stream
        if user not in role.members.all():
            role.members.add(user)
        user._is_system_auditor = True
    else:
        role = Role.singleton('system_auditor')
        if user in role.members.all():
            role.members.remove(user)
        user._is_system_auditor = False


User.add_to_class('is_system_auditor', user_is_system_auditor)


def user_is_in_enterprise_category(user, category):
    ret = (category,) in user.enterprise_auth.values_list('provider') and not user.has_usable_password()
    # NOTE: this if-else block ensures existing enterprise users are still able to
    # log in. Remove it in a future release
    if category == 'radius':
        ret = ret or not user.has_usable_password()
    elif category == 'saml':
        ret = ret or user.social_auth.all()
    return ret


User.add_to_class('is_in_enterprise_category', user_is_in_enterprise_category)


def o_auth2_application_get_absolute_url(self, request=None):
    return reverse('api:o_auth2_application_detail', kwargs={'pk': self.pk}, request=request)


OAuth2Application.add_to_class('get_absolute_url', o_auth2_application_get_absolute_url)


def o_auth2_token_get_absolute_url(self, request=None):
    return reverse('api:o_auth2_token_detail', kwargs={'pk': self.pk}, request=request)


OAuth2AccessToken.add_to_class('get_absolute_url', o_auth2_token_get_absolute_url)

from awx.main.registrar import activity_stream_registrar  # noqa

activity_stream_registrar.connect(Organization)
activity_stream_registrar.connect(Inventory)
activity_stream_registrar.connect(Host)
activity_stream_registrar.connect(Group)
activity_stream_registrar.connect(Instance)
activity_stream_registrar.connect(InstanceGroup)
activity_stream_registrar.connect(InventorySource)
# activity_stream_registrar.connect(InventoryUpdate)
activity_stream_registrar.connect(Credential)
activity_stream_registrar.connect(CredentialType)
activity_stream_registrar.connect(Team)
activity_stream_registrar.connect(Project)
# activity_stream_registrar.connect(ProjectUpdate)
activity_stream_registrar.connect(ExecutionEnvironment)
activity_stream_registrar.connect(JobTemplate)
activity_stream_registrar.connect(Job)
activity_stream_registrar.connect(AdHocCommand)
# activity_stream_registrar.connect(JobHostSummary)
# activity_stream_registrar.connect(JobEvent)
# activity_stream_registrar.connect(Profile)
activity_stream_registrar.connect(Schedule)
activity_stream_registrar.connect(NotificationTemplate)
activity_stream_registrar.connect(Notification)
activity_stream_registrar.connect(Label)
activity_stream_registrar.connect(User)
activity_stream_registrar.connect(WorkflowJobTemplate)
activity_stream_registrar.connect(WorkflowJobTemplateNode)
activity_stream_registrar.connect(WorkflowJob)
activity_stream_registrar.connect(WorkflowApproval)
activity_stream_registrar.connect(WorkflowApprovalTemplate)
activity_stream_registrar.connect(OAuth2Application)
activity_stream_registrar.connect(OAuth2AccessToken)

# prevent API filtering on certain Django-supplied sensitive fields
prevent_search(User._meta.get_field('password'))
prevent_search(OAuth2AccessToken._meta.get_field('token'))
prevent_search(RefreshToken._meta.get_field('token'))
prevent_search(OAuth2Application._meta.get_field('client_secret'))
prevent_search(OAuth2Application._meta.get_field('client_id'))
prevent_search(Grant._meta.get_field('code'))
