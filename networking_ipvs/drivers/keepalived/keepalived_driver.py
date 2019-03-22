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

import copy
import hashlib
import os

from neutron.agent.linux import utils
from oslo_log import log as logging
from oslo_utils import fileutils

from networking_ipvs._i18n import _LE
from networking_ipvs.common import constants as const
from networking_ipvs.common import rpc
from networking_ipvs.common import template
from networking_ipvs.drivers.common import nic_driver
from networking_ipvs.drivers.common import revision
from networking_ipvs.drivers.common import utils as ipvs_utils
from networking_ipvs.drivers.keepalived import utils as kutils

LOG = logging.getLogger(__name__)


class ConfigDriver(template.KeepalivedTemplate):

    def __init__(self, conf):
        super(ConfigDriver, self).__init__(conf)
        self.keepalived_conf_path = self.conf.keepalived.keepalived_conf_path

    def _replace_file(self, content, file_path):
        dir_path = file_path.rsplit(os.sep, 1)[0]
        tmp_file = fileutils.write_to_tempfile(content, dir_path)
        os.chmod(tmp_file, 0o644)
        os.rename(tmp_file, file_path)

    def _update_keepalived_main(self):
        self._replace_file(self.get_main_conf(), self.keepalived_conf_path)

    def _get_file_path(self, vs_info):
        file_path = os.path.join(
            self.vs_conf_path,
            '%s_%s' % (vs_info[const.LISTEN_IP], vs_info[const.LISTEN_PORT]))
        if not vs_info[const.ADMIN_STATE_UP]:
            file_path = file_path + const.DOWN
        return file_path

    def update(self, vs_info, realservers):
        file_path = self._get_file_path(vs_info)
        if file_path.endswith(const.DOWN):
            up_file_path = file_path[:-5]
            if os.path.isfile(up_file_path):
                os.remove(up_file_path)
        else:
            down_file_path = file_path + const.DOWN
            if os.path.isfile(down_file_path):
                os.remove(down_file_path)
        if realservers:
            self._replace_file(
                self.get_virtualserver_conf(vs_info, realservers), file_path)
        self._update_keepalived_main()

    def delete(self, vs_info):
        file_path = self._get_file_path(vs_info)
        os.remove(file_path)
        self._update_keepalived_main()


class ConfigManager(ConfigDriver):

    def __init__(self, conf):
        super(ConfigManager, self).__init__(conf)
        fileutils.ensure_tree(self.vs_conf_path)
        self._init_vs_cache()
        self._new_vips = set()
        self._stale_vips = set()

    def _init_vs_cache(self):
        self._vs_cache = {}
        for f in os.listdir(self.vs_conf_path):
            vs = kutils.parse_virtualserver_conf(
                os.path.join(self.vs_conf_path, f))
            if not vs:
                continue
            vs[const.ADMIN_STATE_UP] = f[-5:] != const.DOWN
            listen_ip, listen_port = vs[const.LISTEN_IP], vs[const.LISTEN_PORT]
            if listen_ip not in self._vs_cache:
                self._vs_cache[listen_ip] = {}
            self._vs_cache[listen_ip][listen_port] = vs

    def _is_vip_down(self, listen_ip):
        if listen_ip not in self._vs_cache:
            return True
        down = False
        for vs in self._vs_cache[listen_ip].values():
            if vs[const.ADMIN_STATE_UP] and any(
                    rs[const.ADMIN_STATE_UP]
                    for rs in vs[const.REALSERVERS].values()):
                break
        else:
            down = True
        return down

    def _update_vs_cache(self, vs_info, realservers=None):
        lip, lport = vs_info[const.LISTEN_IP], vs_info[const.LISTEN_PORT]
        was_vip_down = self._is_vip_down(lip)
        if lip not in self._vs_cache:
            self._vs_cache[lip] = {}
        if lport not in self._vs_cache[lip]:
            self._vs_cache[lip][lport] = vs_info
            self._vs_cache[lip][lport][const.REALSERVERS] = {}
        self._vs_cache[lip][lport].update(vs_info)
        if realservers:
            for rs in realservers:
                rs_key = '%s:%s' % (rs[const.SERVER_IP], rs[const.SERVER_PORT])
                self._vs_cache[lip][lport][const.REALSERVERS].setdefault(
                    rs_key, {})
                self._vs_cache[lip][lport][const.REALSERVERS].get(
                    rs_key).update(rs)
        elif const.ADMIN_STATE_UP in vs_info:
            for rs in self._vs_cache[lip][lport][const.REALSERVERS].values():
                rs[const.ADMIN_STATE_UP] = vs_info[const.ADMIN_STATE_UP]
        is_vip_down = self._is_vip_down(lip)
        if was_vip_down and not is_vip_down:
            self._new_vips.add(lip)
        elif not was_vip_down and is_vip_down:
            self._stale_vips.add(lip)

    def _delete_rs_from_cache(self, vs_info, realservers):
        listen_ip = vs_info[const.LISTEN_IP]
        listen_port = vs_info[const.LISTEN_PORT]
        for rs in realservers:
            rs_key = '%s:%s' % (rs[const.SERVER_IP], rs[const.SERVER_PORT])
            self._vs_cache.get(listen_ip, {}).get(listen_port, {}).get(
                const.REALSERVERS, {}).pop(rs_key, None)

    def _delete_vs_from_cache(self, vs_info):
        listen_ip = vs_info[const.LISTEN_IP]
        listen_port = vs_info[const.LISTEN_PORT]
        vs_info = self._vs_cache.get(listen_ip, {}).pop(listen_port, None)
        if not self._vs_cache.get(listen_ip):
            if listen_ip in self._vs_cache:
                self._vs_cache.pop(listen_ip)
                self._stale_vips.add(listen_ip)
        return vs_info

    def _get_vs_info(self, vs_info):
        listen_ip = vs_info[const.LISTEN_IP]
        listen_port = vs_info[const.LISTEN_PORT]
        ret = {
            k: self._vs_cache.get(listen_ip, {}).get(listen_port, {}).get(k)
            for k in (const.FORWARD_METHOD, const.SCHEDULER,
                      const.ADMIN_STATE_UP)}
        ret.update({
            const.LISTEN_IP: listen_ip, const.LISTEN_PORT: listen_port})
        return ret

    def _get_realservers(self, vs_info):
        listen_ip = vs_info[const.LISTEN_IP]
        listen_port = vs_info[const.LISTEN_PORT]
        return self._vs_cache.get(listen_ip, {}).get(listen_port, {}).get(
            const.REALSERVERS, {}).values()

    def get_vips(self):
        return self._vs_cache.keys()

    def get_changed_vips(self):
        new_vips = copy.copy(self._new_vips)
        stale_vips = copy.copy(self._stale_vips)
        self._new_vips.clear()
        self._stale_vips.clear()
        return new_vips, stale_vips

    def update(self, vs_info, realservers=None):
        self._update_vs_cache(vs_info, realservers)
        realservers = self._get_realservers(vs_info)
        vs_info = self._get_vs_info(vs_info)
        super(ConfigManager, self).update(vs_info, realservers)

    def delete_rs(self, vs_info, realservers):
        self._delete_rs_from_cache(vs_info, realservers)
        realservers = self._get_realservers(vs_info)
        if not realservers:
            self.delete_vs(vs_info)
        else:
            vs_info = self._get_vs_info(vs_info)
            super(ConfigManager, self).update(vs_info, realservers)

    def delete_vs(self, vs_info):
        vs_info = self._delete_vs_from_cache(vs_info)
        if vs_info:
            super(ConfigManager, self).delete(vs_info)

    def get_vs_conf_md5(self, vs_info):
        file_path = self._get_file_path(vs_info)
        md5 = 0
        if os.path.isfile(file_path):
            md5 = hashlib.md5(open(file_path).read()).hexdigest()
        return md5


class IPVSDriver(rpc.PluginNotifyEndpoint):

    def __init__(self, conf, rpc_plugin):

        self.conf = conf
        self.rpc_plugin = rpc_plugin
        self._fullnat_check()
        self._config = ConfigManager(conf)
        self._revision = revision.RevisionHelper(
            conf, rpc_plugin, self._revision_delete_callback,
            self._revision_update_callback)
        self._nic = nic_driver.NICDriver(conf)
        self.start_ipvs_sync_daemon()

    def start_ipvs_sync_daemon(self):
        ipvs_utils.init_sync_daemon(
            self.conf.ipvs.ipvs_sync_daemon_nic,
            self.conf.ipvs.ipvs_sync_daemon_ids,
            self._execute)

    def _fullnat_check(self):
        self._enable_fullnat = False
        if self.conf.ipvs.enable_ipvs_fullnat:
            if ipvs_utils.os_support_fullnat(self._execute):
                self._enable_fullnat = True
        if self._enable_fullnat:
            self.name = const.IPVS_FULLNAT
        else:
            self.name = const.IPVS

    def _execute(self, cmd, extra_ok_codes=None, reraise=False):
        try:
            return utils.execute(cmd, run_as_root=True,
                                 extra_ok_codes=extra_ok_codes)
        except RuntimeError as e:
            msg = _LE("Keepalived driver failed to execute %(cmd)s, get "
                      "error message %(err)s") % {'cmd': cmd, 'err': e.message}
            LOG.error(msg)
            if reraise:
                raise e

    def reload_keepalived(func):
        def wrap(self, *args, **kwargs):
            func(self, *args, **kwargs)
            try:
                ret = self._execute(['service', 'keepalived', 'reload'],
                                    reraise=True)
                if 'FAILED' in ret:
                    raise RuntimeError(ret)
            except RuntimeError:
                msg = _LE("Failed to reload keepalived, try restart")
                LOG.error(msg)
                try:
                    self._execute(['service', 'keepalived', 'restart'],
                                  reraise=True)
                except RuntimeError as e:
                    msg = _LE("Failed to restart keepalived.")
                    LOG.error(msg)
                    raise e
        return wrap

    def manage_vip(func):
        def wrap(self, *args, **kwargs):
            func(self, *args, **kwargs)
            to_add, to_delete = self._config.get_changed_vips()
            for vip in to_add:
                self._nic.try_plug_vip(vip)
            for vip in to_delete:
                self._nic.try_unplug_vip(vip)
        return wrap

    def _md5_check_failed(self, vs_info, md5):
        return md5 != self._config.get_vs_conf_md5(vs_info)

    def md5_check(func):
        def wrap(self, *args, **kwargs):
            data = args[1]
            vs_info = {
                k: data[k] for k in (const.LISTEN_IP, const.LISTEN_PORT)}
            vs_info.update({
                const.ADMIN_STATE_UP: data.get(const.ADMIN_STATE_UP, True)})
            md5, timestamp = self._get_revision_keys(data)
            func(self, *args, **kwargs)
            if self._md5_check_failed(vs_info, md5):
                self._revision.update_with_upstream(end=timestamp)
        return wrap

    def _revision_delete_callback(self, vs_info, realservers):
        if realservers:
            self._config.delete_rs(vs_info, realservers)
        else:
            self._config.delete_vs(vs_info)

    def _revision_update_callback(self, vs_info, realservers):
        self._config.update(vs_info, realservers)

    @reload_keepalived
    @manage_vip
    def sync_state(self):
        self._revision.update_with_upstream()

    def _get_revision_keys(self, data):
        return data.pop(const.MD5), data.pop(const.TIMESTAMP, None)

    @reload_keepalived
    @manage_vip
    def update_virtualservers(self, context, virtualservers):
        need_sync = False
        timestamp = virtualservers[const.TIMESTAMP]
        if virtualservers[const.ADMIN_STATE_UP]:
            for vs in virtualservers[const.VIRTUALSERVERS].values():
                md5, _ = self._get_revision_keys(vs)
                realservers = vs.pop(const.REALSERVERS)
                self._config.update(vs, realservers)
                if self._md5_check_failed(vs, md5):
                    need_sync = True
                    break
        else:
            for vs in virtualservers[const.VIRTUALSERVERS].values():
                md5, _ = self._get_revision_keys(vs)
                vs.update({const.ADMIN_STATE_UP: False})
                self._config.update(vs)
                if self._md5_check_failed(vs, md5):
                    need_sync = True
                    break
        if need_sync:
            self._revision.update_with_upstream(end=timestamp)

    @reload_keepalived
    @manage_vip
    def delete_virtualservers(self, context, virtualservers):
        timestamp = virtualservers[const.TIMESTAMP]
        for vs in virtualservers[const.VIRTUALSERVERS].values():
            self._config.delete_vs(vs)

    @reload_keepalived
    @manage_vip
    @md5_check
    def update_virtualserver(self, context, virtualserver):
        self._config.update(virtualserver)

    @reload_keepalived
    @manage_vip
    def delete_virtualserver(self, context, virtualserver):
        timestamp = virtualserver[const.TIMESTAMP]
        self._config.delete_vs(virtualserver)

    def _prepare_rs_data(self, realserver):
        vs_info = {k: realserver[k] for k in (
            const.LISTEN_IP, const.LISTEN_PORT, const.SCHEDULER,
            const.FORWARD_METHOD)
            if k in realserver}
        vs_info.update({const.ADMIN_STATE_UP: True})
        return vs_info, realserver

    @reload_keepalived
    @manage_vip
    @md5_check
    def create_realserver(self, context, realserver):
        vs_info, realserver = self._prepare_rs_data(realserver)
        self._config.update(vs_info, [realserver])

    @reload_keepalived
    @manage_vip
    @md5_check
    def update_realserver(self, context, realserver):
        vs_info, realserver = self._prepare_rs_data(realserver)
        self._config.update(vs_info, [realserver])

    @reload_keepalived
    @manage_vip
    @md5_check
    def delete_realserver(self, context, realserver):
        vs_info, realserver = self._prepare_rs_data(realserver)
        self._config.delete_rs(vs_info, [realserver])
