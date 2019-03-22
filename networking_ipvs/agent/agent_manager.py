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

from neutron import context as ncontext
from neutron.services import provider_configuration as provconfig
from oslo_log import log as logging
from oslo_service import periodic_task
from oslo_utils import importutils

from networking_ipvs._i18n import _, _LE
from networking_ipvs.common import rpc
from networking_ipvs.common import constants as const

LOG = logging.getLogger(__name__)


class AgentManager(rpc.PluginNotifyEndpoint,
                   periodic_task.PeriodicTasks):

    def __init__(self, conf, init=0):
        super(AgentManager, self).__init__(conf)
        self.conf = conf
        self.context = ncontext.get_admin_context_without_session()
        self.plugin_rpc = rpc.PluginRPCClient(self.context, self.conf.host)
        self._load_driver()

        self.agent_state = {
            'binary': 'networking-ipvs-agent',
            'host': conf.host,
            'topic': const.NETWORKING_IPVS_AGENT,
            'configurations': {'device_driver': self.driver.name},
            'agent_type': const.NETWORKING_IPVS_AGENT_TYPE,
            'start_flag': True}

        self.state_rpc = rpc.setup_state_report_rpc(
            self.conf.AGENT.report_interval, self._report_state)
        self.sync_state()

    def _load_driver(self):
        driver_cls = provconfig.get_provider_driver_class(
            self.conf.device_driver, const.DEVICE_DRIVER)
        try:
            self.driver = importutils.import_object(
                driver_cls, self.conf, self.plugin_rpc)
        except ImportError:
            msg = _('Error importing loadbalancer device driver: %s')
            raise SystemExit(msg % driver_cls)

    def _report_state(self):
        try:
            self.state_rpc.report_state(self.context, self.agent_state)
            self.agent_state.pop('start_flag', None)
        except Exception:
            LOG.exception(_LE("Failed reporting state!"))

    def sync_state(self):
        self.driver.sync_state()

    def update_virtualservers(self, context, virtualservers):
        self.driver.update_virtualservers(context, virtualservers)

    def delete_virtualservers(self, context, virtualservers):
        self.driver.delete_virtualservers(context, virtualservers)

    def update_virtualserver(self, context, virtualserver):
        self.driver.update_virtualserver(context, virtualserver)

    def delete_virtualserver(self, context, virtualserver):
        self.driver.delete_virtualserver(context, virtualserver)

    def create_realserver(self, context, realserver):
        self.driver.create_realserver(context, realserver)

    def update_realserver(self, context, realserver):
        self.driver.update_realserver(context, realserver)

    def delete_realserver(self, context, realserver):
        self.driver.delete_realserver(context, realserver)

    def delete_realservers(self, context, realservers):
        self.driver.delete_realservers(context, realservers)
