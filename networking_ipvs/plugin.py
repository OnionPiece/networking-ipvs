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

import six

from neutron.db import agents_db
from oslo_config import cfg
from oslo_log import log as logging

from networking_ipvs._i18n import _LI, _LE
from networking_ipvs.common import constants as const
from networking_ipvs.common import exceptions as ipvs_exc
from networking_ipvs.common import rpc
from networking_ipvs.common import utils
from networking_ipvs.db import networking_ipvs_db as ipvs_db
from networking_ipvs.extensions import networkingipvs as ipvs_ext

LOG = logging.getLogger(__name__)


class NetworkingIPVSPlugin(ipvs_db.NetworkingIPVSPluginDb,
                           agents_db.AgentDbMixin,
                           rpc.PluginMQNotifyMech):
    """Implementation of the Networking IPVS Service Plugin."""

    supported_extension_aliases = ["networking_ipvs"]
    path_prefix = ipvs_ext.NETWORKING_IPVS_PREFIX

    def __init__(self):
        self._rpc_extensions = [
            rpc.PluginRPC(self),
            agents_db.AgentExtRpcCallback(self)
        ]
        self.conn = rpc.start_rpc_listener(const.NETWORKING_IPVS_PLUGIN,
                                           self._rpc_extensions)
        self._notifier = rpc.PluginNotifier()

    def _admin_state_check(self, update_req):
        req_type, body = update_req.items()[0]
        raise_err = False
        if const.ADMIN_STATE_UP in body and len(body) > 1:
            raise_err = True
            body = {const.ADMIN_STATE_UP: body[const.ADMIN_STATE_UP]}
        return {req_type: body}, raise_err

    def _force_delete(deletor):
        def _delete(self, *args, **kwargs):
            force = kwargs.get('body', {}).get('force', False)
            return deletor(self, *args, force=force)
        return _delete

    def _clean_neutron_port(deletor):
        def wrap(self, *args, **kwargs):
            ret = deletor(self, *args, **kwargs)
            context = args[0].elevated()
            clean_vips = []
            if const.VIRTUALSERVERS in ret:
                ports = {
                    vs[const.LISTEN_IP]: vs['neutron_port_id']
                    for vs in ret[const.VIRTUALSERVERS]}
            else:
                ports = {ret[const.LISTEN_IP]: ret['neutron_port_id']}
            alive_ips = set([
                vs[const.LISTEN_IP]
                for vs in self._db_gets(
                    context, const.IPVS_VIRTUALSERVER,
                    filters={const.LISTEN_IP: ports.keys()})])
            stale_port_ids = [ports[i] for i in ports if i not in alive_ips]
            if stale_port_ids:
                self._core_plugin._delete_ports(context, stale_port_ids)
            return ret
        return wrap

    def _scheduler_format(operator):
        def _format(self, *args, **kwargs):
            do_fmt = kwargs.pop('format_scheduler', True)
            ret = operator(self, *args, **kwargs)
            if do_fmt:
                utils.scheduler_format(ret)
            return ret
        return _format

    def create_ipvs_loadbalancer(self, context, ipvs_loadbalancer):
        return self._db_create(context, ipvs_loadbalancer)

    def update_ipvs_loadbalancer(self, context, id, ipvs_loadbalancer):
        ipvs_loadbalancer, warn = self._admin_state_check(ipvs_loadbalancer)
        res = self._db_update(context, id, ipvs_loadbalancer)
        self._notify(context, const.IPVS_LOADBALANCER, const.UPDATE, res)
        if warn:
            raise ipvs_exc.AdminStateUpCannotUpdateWithOtherAttr()
        return res

    @_clean_neutron_port
    @_force_delete
    def delete_ipvs_loadbalancer(self, context, id, force=False):
        res = self._db_delete(context, const.IPVS_LOADBALANCER, id, force)
        self._notify(context, const.IPVS_LOADBALANCER, const.DELETE, res)
        return res

    def get_ipvs_loadbalancer(self, context, id, fields=None):
        return self._db_get(context, const.IPVS_LOADBALANCER, id, fields)

    def get_ipvs_loadbalancers(self, context, filters=None, fields=None):
        return self._db_gets(context, const.IPVS_LOADBALANCER,
                             filters, fields)

    @_scheduler_format
    def create_ipvs_virtualserver(self, context, ipvs_virtualserver):
        data = ipvs_virtualserver[const.IPVS_VIRTUALSERVER]
        data.update(utils.get_port_for_virtualserver(
            context, self._core_plugin, data))
        return self._db_create(context, {const.IPVS_VIRTUALSERVER: data})

    @_scheduler_format
    def update_ipvs_virtualserver(self, context, id, ipvs_virtualserver):
        ipvs_virtualserver, warn = self._admin_state_check(ipvs_virtualserver)
        res = self._db_update(context, id, ipvs_virtualserver)
        self._notify(context, const.IPVS_VIRTUALSERVER, const.UPDATE, res,
                     ipvs_virtualserver[const.IPVS_VIRTUALSERVER])
        if warn:
            raise ipvs_exc.AdminStateUpCannotUpdateWithOtherAttr()
        return res

    @_scheduler_format
    @_clean_neutron_port
    @_force_delete
    def delete_ipvs_virtualserver(self, context, id, force=False):
        res = self._db_delete(context, const.IPVS_VIRTUALSERVER, id, force)
        self._notify(context, const.IPVS_VIRTUALSERVER, const.DELETE, res)
        return res

    @_scheduler_format
    def get_ipvs_virtualserver(self, context, id, fields=None):
        return self._db_get(context, const.IPVS_VIRTUALSERVER, id, fields)

    @_scheduler_format
    def get_ipvs_virtualservers(self, context, filters=None, fields=None):
        return self._db_gets(context, const.IPVS_VIRTUALSERVER,
                             filters, fields)

    def create_ipvs_realserver(self, context, ipvs_realserver):
        res = self._db_create(context, ipvs_realserver)
        self._notify(context, const.IPVS_REALSERVER, const.CREATE, res)
        return res

    def update_ipvs_realserver(self, context, id, ipvs_realserver):
        ipvs_realserver, warn = self._admin_state_check(ipvs_realserver)
        res = self._db_update(context, id, ipvs_realserver)
        self._notify(context, const.IPVS_REALSERVER, const.UPDATE, res,
                     ipvs_realserver[const.IPVS_REALSERVER])
        if warn:
            raise ipvs_exc.AdminStateUpCannotUpdateWithOtherAttr()
        return res

    def delete_ipvs_realserver(self, context, id):
        res = self._db_delete(context, const.IPVS_REALSERVER, id)
        self._notify(context, const.IPVS_REALSERVER, const.DELETE, res)
        return res

    def get_ipvs_realserver(self, context, id, fields=None):
        return self._db_get(context, const.IPVS_REALSERVER, id, fields)

    def get_ipvs_realservers(self, context, filters=None, fields=None):
        return self._db_gets(context, const.IPVS_REALSERVER,
                             filters, fields)

    def create_ipvs_quota(self, context, ipvs_quota):
        if not context.is_admin:
            raise ipvs_exc.OnlyAdminCanSetOtherTenantQuota()
        return self.set_quota(context, ipvs_quota)

    def get_ipvs_quotas(self, context, filters=None, fields=None):
        quotas = self.get_quotas(context, filters or {}, fields)
        used = self._db_get_usage(context, filters or {})
        for q in quotas:
            q[const.QUOTA_USAGE] = used[q[const.QUOTA_TYPE]]
        return quotas
