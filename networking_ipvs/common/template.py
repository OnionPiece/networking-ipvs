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

import jinja2
import os

from networking_ipvs.common import constants as const
from networking_ipvs.drivers.keepalived import templates


class VirtualServerTemplate(object):

    def __init__(self):
        template_loader = jinja2.FileSystemLoader(
            searchpath=templates.templates_path)
        self._template_env = jinja2.Environment(
            loader=template_loader, trim_blocks=True, lstrip_blocks=True)

    @property
    def _virtualserver_template(self):
        return self._template_env.get_template(
            templates.virtualserver_template_name)

    def get_virtualserver_conf(self, vs_info, realservers):
        realservers.sort(key=lambda x: x['id'])
        return self._virtualserver_template.render({
            "vs_info": vs_info, "realservers": realservers})


class KeepalivedTemplate(VirtualServerTemplate):

    def __init__(self, conf):
        super(KeepalivedTemplate, self).__init__()
        self.conf = conf
        self.vs_conf_path = self.conf.keepalived.virtualserver_conf_path

    @property
    def _template(self):
        return self._template_env.get_template(
            templates.keepalived_template_name)

    def get_main_conf(self):
        def get_globals():
            notify_emails = self.conf.keepalived.notify_emails
            if not notify_emails:
                return {}
            return {
                "notify_emails": self.conf.keepalived.notify_emails,
                "notify_from": self.conf.keepalived.notify_from,
                "smtp_server": self.conf.keepalived.smtp_server,
                "smtp_timeout": self.conf.keepalived.smtp_timeout}

        return self._template.render({
            "globals": get_globals(),
            "virtualservers": [
                f for f in os.listdir(self.vs_conf_path)
                if f[-5:] != const.DOWN],
            "os_sep": os.sep,
            "include_path": self.vs_conf_path})
