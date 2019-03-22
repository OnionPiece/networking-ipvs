# Copyright 2018
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from oslo_config import cfg

from networking_ipvs._i18n import _
from networking_ipvs.common import constants as const
from networking_ipvs.drivers.keepalived import templates


KEEPALIVED_DRIVER = (
    'networking_ipvs.drivers.keepalived.keepalived_driver.IPVSDriver')
AGENT_OPTS = [
    cfg.IntOpt(
        'periodic_interval',
        default=15,
        help=_('Seconds between periodic task runs')
    ),
    cfg.StrOpt(
        const.DEVICE_DRIVER,
        default=KEEPALIVED_DRIVER,
        help=_('Drivers used to manage loadbalancing devices'),
    ),
]


DRIVER_OPTS = [
    cfg.StrOpt(
        'ipvs_vip_nic_mapping',
        default='*:eth0',
        help=_('NICs to add ipvs vip on'),
    ),
    cfg.StrOpt(
        'ipvs_sync_daemon_nic',
        default='',
        help=_('NIC to start ipvs sync daemon'),
    ),
    cfg.StrOpt(
        'ipvs_sync_daemon_ids',
        default='',
        help=_('Sync daemon ids in format master-id:slave-ids. E.g. 1:2,3'),
    ),
    cfg.BoolOpt(
        'enable_ipvs_fullnat',
        default=True,
        help=_('Enable ipvs fullnat on agent or not, default True.'
               'Need kernel support ipvs fullnat first. Must be True on '
               'kernel with Alibaba fullnat patched.'),
    ),
]


REVISION_OPTS = [
    cfg.StrOpt(
        'revision_path',
        default='/var/lib/neutron/networking_ipvs_revision',
        help=_('Path to store revision'),
    ),
]


KEEPALIVED_DRIVER_OPTS = [
    cfg.StrOpt(
        'keepalived_conf_path',
        default='/etc/keepalived/keepalived.conf',
        help=_('Keepalived service conf path'),
    ),
    cfg.StrOpt(
        'virtualserver_conf_path',
        default='/etc/keepalived/networking_ipvs',
        help=_('Path for per ipvs loadbalancer keepalived conf'),
    ),
    cfg.ListOpt(
        'notify_emails',
        default=[],
        help=_('notification_email(s) in keepalived.conf'),
    ),
    cfg.StrOpt(
        'notify_from',
        default='',
        help=_('notification_email_from in keepalived.conf'),
    ),
    cfg.StrOpt(
        'smtp_server',
        default='',
        help=_('smtp_server in keepalived.conf'),
    ),
    cfg.IntOpt(
        'smtp_timeout',
        default=30,
        help=_('smtp_connect_timeout in keepalived.conf'),
    ),
]
