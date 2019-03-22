# Copyright 2018
# All Rights Reserved.
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

from neutron_lib import exceptions as nexception
from oslo_log import log as logging

from networking_ipvs._i18n import _


LOG = logging.getLogger(__name__)


class RevisionCannotWork(nexception.NeutronException):
    message = _("Revision sub-system cannot work. Need to fetch all data.")


class ResourceNotFound(nexception.NotFound):
    message = _("%(resource_kind)s kind of resource with id %(id)s not found.")


class VirtualServerEntityExists(nexception.Conflict):
    message = _("A virtualserver entity with %(listen_ip)s:%(listen_port)s on "
                "%(neutron_network_id)s already exists.")


class RealServerEntityExists(nexception.Conflict):
    message = _("A realserver entity with %(server_ip)s:%(server_port)s on "
                "%(ipvs_virtualserver_id)s already exists.")


class ResourceInUse(nexception.InUse):
    message = _("Resource %(resource)s with id %(id)s is in use.")


class AdminStateUpCannotUpdateWithOtherAttr(nexception.BadRequest):
    message = _("Admin_state_up cannot be updated with other attributes. "
                "Will update admin_state_up, but ignore other attrs.")


class OnlyAdminCanSetOtherTenantQuota(nexception.BadRequest):
    message = _("Only admin can set other tenant quota.")


class QuotaExceed(nexception.Conflict):
    message = _("Quota exceed.")
