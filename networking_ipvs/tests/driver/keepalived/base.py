#!/usr/bin/python2.7

import os

from neutron.agent.linux import ip_lib

from networking_ipvs.common import template
from networking_ipvs.common import constants as const


class FakeConf(object):
    @property
    def keepalived(self):
        class TemplateConf(object):
            @property
            def keepalived_conf_path(self):
                return "/etc/keepalived/keepalived.conf"

            @property
            def virtualserver_conf_path(self):
                return "/etc/keepalived/networking_ipvs"

            @property
            def notify_emails(self):
                return ["admin1@cn", "admin2@cn"]

            @property
            def notify_from(self):
                return "lvs_cluster@cn"

            @property
            def smtp_server(self):
                return "192.168.0.1"

            @property
            def smtp_timeout(self):
                return 30
        return TemplateConf()

    @property
    def ipvs(self):
        class Fake(object):
            @property
            def enable_ipvs_fullnat(self):
                return False

            @property
            def ipvs_vip_nic_mapping(self):
                return '*:eth0'

            @property
            def ipvs_sync_daemon_nic(self):
                return ''

            @property
            def ipvs_sync_daemon_ids(self):
                return ''
        return Fake()

    @property
    def revision(self):
        class Fake(object):
            @property
            def revision_path(self):
                return '/var/lib/neutron/networking_ipvs_revision'
        return Fake()


class FakeRPC(object):
    def __init__(self, context, plugin):
        self.context = context
        self.plugin = plugin

    def get_revisions(self, start=None, end=None):
        return self.plugin.get_revisions(self.context, start, end)

    def get_ipvs_realservers(self, filters=None):
        return self.plugin.get_ipvs_realservers(self.context, filters)

    def get_ipvs_virtualservers(self, filters=None):
        return self.plugin.get_ipvs_virtualservers(self.context, filters)


conf = FakeConf()
template_driver = template.KeepalivedTemplate(conf)


def cleanup():
    for f in os.listdir(conf.keepalived.virtualserver_conf_path):
        os.remove(os.path.join(conf.keepalived.virtualserver_conf_path, f))
    eth0 = ip_lib.IPDevice('eth0')
    for addr in eth0.addr.list():
        if addr['cidr'].endswith('/32'):
            eth0.addr.delete(addr['cidr'])
    os.system('service keepalived restart')


# TODO: update for md5 check
def _md5_check_failed(*args, **kwargs):
    return False


fake_md5_check = _md5_check_failed


def assert_vip(ip, exists=True):
    _ip = ip + '/32'
    eth0 = ip_lib.IPDevice('eth0')
    ip_list = [addr['cidr'] for addr in eth0.addr.list()]
    if exists:
        assert _ip in ip_list
    else:
        assert _ip not in ip_list


def assert_vs_file(vs_info, all_rs):
    listen_ip = vs_info[const.LISTEN_IP]
    listen_port = vs_info[const.LISTEN_PORT]
    file_path = os.path.join(conf.keepalived.virtualserver_conf_path,
                             '%s_%s' % (listen_ip, listen_port))
    up = vs_info.get(const.ADMIN_STATE_UP, True)
    if not up:
        file_path += const.DOWN
    if len(all_rs):
        file_content = None
        temp_content = None
        try:
            assert os.path.isfile(file_path)
            file_content = open(file_path).read()
            temp_content = template_driver.get_virtualserver_conf(
                vs_info, all_rs)
            assert file_content == temp_content
        except AssertionError as e:
            raise AssertionError(
                'file_path: %s\nfile_content:\n%s\ntemp_content:\n%s' % (
                    file_path, file_content, temp_content))
    else:
        assert os.path.exists(file_path) is False


def common_assert(vs_info, all_rs, task_msg, vip_exists=True):
    try:
        assert_vip(vs_info[const.LISTEN_IP], vip_exists)
    except AssertionError:
        print task_msg + ".assert_vip....failed"
        os.sys.exit(1)
    else:
        print task_msg + ".assert_vip....passed"
        try:
            assert_vs_file(vs_info, all_rs)
        except AssertionError as e:
            print task_msg + ".assert_vs_file....failed"
            print e.message
            os.sys.exit(1)
        else:
            print task_msg + ".assert_vs_file....passed"
