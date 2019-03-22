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

import sys

import eventlet

eventlet.monkey_patch()

from neutron.agent.common import config
from neutron.common import config as common_config
from neutron.common import rpc as n_rpc
from oslo_config import cfg
from oslo_service import service

from networking_ipvs._i18n import _
from networking_ipvs.agent import agent_manager as manager
from networking_ipvs.common import constants
from networking_ipvs.common import config as ipvs_conf


class AgentService(n_rpc.Service):
    def start(self):
        super(AgentService, self).start()
        self.tg.add_timer(
            cfg.CONF.periodic_interval,
            self.manager.run_periodic_tasks,
            None,
            None
        )


def main():
    cfg.CONF.register_opts(ipvs_conf.AGENT_OPTS)
    cfg.CONF.register_opts(ipvs_conf.DRIVER_OPTS, 'ipvs')
    cfg.CONF.register_opts(ipvs_conf.REVISION_OPTS, 'revision')
    cfg.CONF.register_opts(ipvs_conf.KEEPALIVED_DRIVER_OPTS, 'keepalived')
    config.register_interface_driver_opts_helper(cfg.CONF)
    config.register_agent_state_opts_helper(cfg.CONF)
    config.register_root_helper(cfg.CONF)

    common_config.init(sys.argv[1:])
    config.setup_logging()

    mgr = manager.AgentManager(cfg.CONF)
    svc = AgentService(
        host=cfg.CONF.host,
        topic=constants.NETWORKING_IPVS_AGENT,
        manager=mgr
    )
    service.launch(cfg.CONF, svc).wait()
