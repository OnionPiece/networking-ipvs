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

import abc
import six

from neutron.agent import rpc as agent_rpc
from neutron.common import rpc as n_rpc
import oslo_messaging
from oslo_service import loopingcall

from networking_ipvs._i18n import _
from networking_ipvs.common import constants as const
from networking_ipvs.common import utils


def start_rpc_listener(topic, endpoints):
    conn = n_rpc.create_connection()
    conn.create_consumer(topic, endpoints, fanout=False)
    conn.consume_in_threads()
    return conn


def setup_state_report_rpc(report_interval, report_method):
    rpc = agent_rpc.PluginReportStateAPI(const.NETWORKING_IPVS_PLUGIN)
    if report_interval:
        heartbeat = loopingcall.FixedIntervalLoopingCall(report_method)
        heartbeat.start(interval=report_interval)
    return rpc


class PluginNotifyEndpoint(object):

    def sync_state(self):
        pass

    def update_virtualservers(self, context, virtualservers):
        """
            for admin_state_down, param virtualservers is {
                "virtualservers": {
                    id: {"listen_ip": listen_ip, "listen_port': listen_port,
                         "md5": md5},
                    ...
                    },
                "admin_state_up": admin_state_up,
                "timestamp": timestamp
            }
            for admin_state_up, param virtualservers is {
                "virtualservers": {
                    id: {"listen_ip": listen_ip,
                         "listen_port': listen_port,
                         ...
                         "real_servers: {
                             "id": id,
                             "server_ip": server_ip,
                             "server_port": server_port
                         },
                         "md5": md5
                        },
                    ...,
                    }
                "admin_state_up": admin_state_up,
                "timestamp": timestamp
            }
        """
        pass

    def delete_virtualservers(self, context, virtualservers):
        """
            param virtualservers is {
                "virtualservers": {
                    "id": {"id":id,
                           "listen_ip": listen_ip,
                           "listen_port': listen_port},
                    ...,
                    },
                "timestamp": timestamp,
                "admin_state_up": admin_state_up,
            }
        """
        pass

    def update_virtualserver(self, context, virtualserver):
        """
            param virtualserver is {
                "listen_ip": listen_ip,
                "listen_port': listen_port,
                "timestamp": timestamp,
                "md5": md5,
                ANY_CHANGED_KEYS: NEW_VALUE
            }
            for admin_state_up, param virtualserver is {
                "listen_ip": listen_ip,
                "listen_port': listen_port,
                "scheduler": scheduler,
                "forward_method": forward_method,
                "md5": md5
                "admin_state_up": admin_state_up,
                "timestamp": timestamp
            }
        """
        pass

    def delete_virtualserver(self, context, virtualserver):
        """
            param virtualserver is {
                "listen_ip": listen_ip,
                "listen_port': listen_port,
                "timestamp": timestamp,
            }
        """
        pass

    def create_realserver(self, context, realserver):
        """
            param realserver is {
                "id": id,
                "server_ip": server_ip,
                "server_port": server_port,
                "weight": weight,
                "delay": delay,
                "timeout": timeout,
                "max_retries": max_retries,
                "admin_state_up": admin_state_up,
                "timestamp": timestamp,
                "listen_ip": listen_ip,
                "listen_port': listen_port,
                "scheduler": scheduler,
                "forward_method": forward_method,
                "md5": parent_md5,
            }
        """
        pass

    def update_realserver(self, context, realserver):
        """
            param realserver is {
                "id": id,
                "server_ip": server_ip,
                "server_port": server_port,
                "timestamp": timestamp,
                "listen_ip": listen_ip,
                "listen_port': listen_port,
                "md5": parent_md5,
                ANY_CHANGED_KEYS: NEW_VALUE
            }
        """
        pass

    def delete_realserver(self, context, realserver):
        """
            param realserver is {
                "id": id,
                "server_ip": server_ip,
                "server_port": server_port,
                "timestamp": timestamp,
                "listen_ip": listen_ip,
                "listen_port': listen_port,
                "md5": parent_md5,
            }
        """
        pass


class PluginMQNotifyMech(object):
    """PluginMQNotifyMech notify data body will follow each method parameter
       in PluginNotifyEndpoint
    """

    def _get_data_for_lb(self, data, full_vs_info=False):
        ret = {const.ADMIN_STATE_UP: data[const.ADMIN_STATE_UP]}
        keys = [const.ID, const.LISTEN_IP, const.LISTEN_PORT]
        if full_vs_info:
            keys += [const.REALSERVERS] + const.VIRTUALSERVER_NOTIFY_KEYS
        ret.update({const.VIRTUALSERVERS: {
            vs[const.ID]: {k: vs[k] for k in keys}
            for vs in data[const.VIRTUALSERVERS]}})
        return ret

    def _get_data_for_vs(self, data, changed_keys=[]):
        return {k: data[k] for k in set([
            const.LISTEN_IP, const.LISTEN_PORT]).union(changed_keys)}

    def _get_data_for_rs(self, data, changed_keys=[]):
        ret = {k: data[k] for k in set([
            # ipvs_virtualserver_id is needed by revision
            const.ID, const.SERVER_IP, const.SERVER_PORT,
            'ipvs_virtualserver_id']).union(changed_keys)}
        ret.update({k: data[const.VIRTUALSERVER][k] for k in (
            const.LISTEN_IP, const.LISTEN_PORT)})
        return ret

    def _need_notify(self, context, resource, action, data, update_req=None):
        method = None
        if action == const.CREATE:
            if resource == const.IPVS_REALSERVER:
                if data[const.ADMIN_STATE_UP] and (
                        data[const.VIRTUALSERVER].get(
                            const.ADMIN_STATE_UP)) and data[const.LB_ADMIN]:
                    method = 'create_realserver'
                    vs_info = {k: data[const.VIRTUALSERVER][k] for k in (
                        const.FORWARD_METHOD, const.SCHEDULER)}
                    data = self._get_data_for_rs(
                        data, const.REALSERVER_NOTIFY_KEYS)
                    data.update(vs_info)
        elif action == const.DELETE:
            if resource == const.IPVS_LOADBALANCER:
                if any([vs[const.REALSERVERS]
                        for vs in data[const.VIRTUALSERVERS]]):
                    method = 'delete_virtualservers'
                    data = self._get_data_for_lb(data)
            elif resource == const.IPVS_VIRTUALSERVER:
                if data[const.LB_ADMIN] and data.get(const.REALSERVERS):
                    method = 'delete_virtualserver'
                    data = self._get_data_for_vs(data)
            elif resource == const.IPVS_REALSERVER:
                if data[const.LB_ADMIN] and data[const.VIRTUALSERVER].get(
                        const.ADMIN_STATE_UP):
                    method = 'delete_realserver'
                    data = self._get_data_for_rs(data)
        elif action == const.UPDATE:
            valid_changes = data.get(const.WHAT_CHANGED)
            if not valid_changes:
                return method, data
            if resource == const.IPVS_LOADBALANCER:
                if any([rs[const.REALSERVERS]
                        for rs in data[const.VIRTUALSERVERS]]):
                    if data[const.ADMIN_STATE_UP]:
                        data = self._get_data_for_lb(data, True)
                    else:
                        data = self._get_data_for_lb(data)
                    method = 'update_virtualservers'
            elif resource == const.IPVS_VIRTUALSERVER:
                if data[const.LB_ADMIN]:
                    if const.ADMIN_STATE_UP in update_req and data.get(
                            const.REALSERVERS):
                        if not update_req[const.ADMIN_STATE_UP]:
                            data = self._get_data_for_vs(data, valid_changes)
                        else:
                            # since attributes may changed during admin_state
                            # is down so it's up again, we need send all notify
                            # keys of data to make sure nothing updating left
                            #
                            # for real servers changing during vs down, md5
                            # checking on agent/driver side should trigger
                            # agent/driver to pull missed data
                            data = self._get_data_for_vs(
                                data, const.VIRTUALSERVER_NOTIFY_KEYS)
                        method = 'update_virtualserver'
                    elif data[const.ADMIN_STATE_UP] and any(
                            data.get(const.REALSERVERS, {}).values()):
                        method = 'update_virtualserver'
                        data = self._get_data_for_vs(data, valid_changes)
            elif resource == const.IPVS_REALSERVER:
                if data[const.LB_ADMIN] and data[const.VIRTUALSERVER].get(
                        const.ADMIN_STATE_UP):
                    if const.ADMIN_STATE_UP in update_req:
                        if not update_req[const.ADMIN_STATE_UP]:
                            data = self._get_data_for_rs(data, valid_changes)
                        else:
                            # since attributes may changed during admin_state
                            # is down so it's up again, we need send all notify
                            # keys of data to make sure nothing updating left
                            data = self._get_data_for_rs(
                                data, const.REALSERVER_NOTIFY_KEYS)
                        method = 'update_realserver'
                    elif data[const.ADMIN_STATE_UP]:
                        method = 'update_realserver'
                        data = self._get_data_for_rs(data, valid_changes)
        return method, data

    def _do_notify(self, context, method, *args, **kwargs):
        method = getattr(self._notifier, method)
        method(context, *args, **kwargs)

    def _notify(self, context, resource, action, data, update_req=None):
        res_id = data[const.ID]
        parent_id = data.get(const.VIRTUALSERVER, {}).get(const.ID)
        method, data = self._need_notify(
            context, resource, action, data, update_req)
        if method:
            update_md5 = (
                resource == const.IPVS_REALSERVER or action == const.UPDATE)
            if resource == const.IPVS_REALSERVER and action == const.DELETE:
                resource = const.IPVS_VIRTUALSERVER
                res_id = parent_id
            if update_md5:
                self._update_revisions_md5(context, resource, res_id)
                self._get_notify_revisions(context, resource, res_id, data)
            elif action == const.DELETE:
                data[const.TIMESTAMP] = self._get_timestamp(
                    context, res_id, action)
            self._do_notify(context, method, data)


class PluginNotifier(PluginNotifyEndpoint):
    """Plugin to agent RPC
       Use PluginMQNotifyMech to valid notify and send notifaction
    """

    def __init__(self):
        target = oslo_messaging.Target(topic=const.NETWORKING_IPVS_AGENT,
                                       fanout=True)
        self.client = n_rpc.get_client(target)

    def _notify(self, context, method, fanout=True, host=None, **kwargs):
        if not fanout and host:
            cctxt = self.client.prepare(fanout=fanout, host=host)
        else:
            cctxt = self.client.prepare()
        cctxt.cast(context, method, **kwargs)

    def agent_updated(self, context, admin_state_up, host):
        # WONT DO
        pass

    def sync_state(self):
        pass

    def update_virtualservers(self, context, virtualservers):
        self._notify(context, 'update_virtualservers',
                     virtualservers=virtualservers)

    def delete_virtualservers(self, context, virtualservers):
        self._notify(context, 'delete_virtualservers',
                     virtualservers=virtualservers)

    def update_virtualserver(self, context, virtualserver):
        self._notify(context, 'update_virtualserver',
                     virtualserver=virtualserver)

    def delete_virtualserver(self, context, virtualserver):
        self._notify(context, 'delete_virtualserver',
                     virtualserver=virtualserver)

    def create_realserver(self, context, realserver):
        self._notify(context, 'create_realserver',
                     realserver=realserver)

    def update_realserver(self, context, realserver):
        self._notify(context, 'update_realserver',
                     realserver=realserver)

    def delete_realserver(self, context, realserver):
        self._notify(context, 'delete_realserver',
                     realserver=realserver)


class PluginRPCClient(object):
    """Agent to Plugin RPC"""

    def __init__(self, context, host):
        self.context = context
        self.host = host
        target = oslo_messaging.Target(topic=const.NETWORKING_IPVS_PLUGIN)
        self.client = n_rpc.get_client(target)

    def get_ipvs_virtualservers(self, filters=None):
        cctxt = self.client.prepare()
        return cctxt.call(self.context, 'get_ipvs_virtualservers',
                          filters=filters)

    def get_ipvs_realservers(self, filters=None):
        cctxt = self.client.prepare()
        return cctxt.call(self.context, 'get_ipvs_realservers',
                          filters=filters)

    def get_revisions(self, start, end=None):
        cctxt = self.client.prepare()
        return cctxt.call(self.context, 'get_revisions',
                          start=start, end=end)


class PluginRPC(object):
    """Plugin side callbacks for PluginRPCClient"""

    def __init__(self, plugin):
        self.plugin = plugin

    def get_ipvs_virtualservers(self, context, filters):
        ret = [
            {k: vs[k]
             for k in [const.ID, const.LISTEN_IP,
                       const.LISTEN_PORT] + const.VIRTUALSERVER_NOTIFY_KEYS}
            for vs in self.plugin.get_ipvs_virtualservers(
                context, filters, format_scheduler=False)]
        for vs in ret:
            self.plugin._get_notify_revisions(
                context, const.IPVS_VIRTUALSERVER, vs[const.ID], vs)
        return ret

    def get_ipvs_realservers(self, context, filters):
        return self.plugin.get_ipvs_realservers(context, filters)

    def get_revisions(self, context, start, end):
        return self.plugin.get_revisions(context, start, end)
