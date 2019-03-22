#!/usr/bin/python2.7

import datetime
import hashlib
import netaddr
import os
import sqlalchemy as sa

from neutron.api.v2 import attributes as attr
from neutron import context as ncontext
from neutron.db import agents_db
from neutron import manager
from oslo_utils import uuidutils

from networking_ipvs.common import constants as const
from networking_ipvs.common import rpc
from networking_ipvs.tests.plugin import assert_helper


FAKE_CORE_PLUGIN = None


class FakeAgentExtRpcCallback(object):
    def __init__(self, plugin=None):
        super(FakeAgentExtRpcCallback, self).__init__()
        self.plugin = plugin


class FakePluginNotifier(object):
    def __init__(self):
        pass


class FakeCorePlugin(object):
    def __init__(self, ip_start, ip_end):
        self.ports = {}
        self.ip_pool = iter(netaddr.IPRange(ip_start, ip_end))

    def get_ports(self, context, filters):
        net_id = filters['network_id']
        ip = filters['fixed_ips']['ip_address']
        return [p for p in self.ports.values()
                if p['network_id'] == net_id and p['ip'] == ip]

    def create_port(self, context, req):
        port = req['port']
        net_id = port['network_id']
        ip = port['fixed_ips']
        if ip == attr.ATTR_NOT_SPECIFIED:
            ip = str(self.ip_pool.next())
        else:
            ip = ip[0]['ip_address']
        port_id = uuidutils.generate_uuid()
        self.ports[port_id] = {'network_id': net_id, 'ip': ip}
        return {'fixed_ips': [{'ip_address': ip}],
                'id': port_id}

    def _delete_ports(self, context, port_ids):
        for i in port_ids:
            self.ports.pop(i, None)


class FakeManager(object):
    @classmethod
    def get_plugin(cls):
        global FAKE_CORE_PLUGIN
        if not FAKE_CORE_PLUGIN:
            net_ip_start = '192.168.100.10'
            net_ip_end = '192.168.100.200'
            FAKE_CORE_PLUGIN = FakeCorePlugin(net_ip_start, net_ip_end)
        return FAKE_CORE_PLUGIN


def fake_start_rpc_listener(*args): pass


manager.NeutronManager = FakeManager
agents_db.AgentExtRpcCallback = FakeAgentExtRpcCallback
rpc.start_rpc_listener = fake_start_rpc_listener
rpc.PluginNotifier = FakePluginNotifier


def db_init():
    context = ncontext.get_admin_context()
    resource_types = sa.Enum(*const.SUPPORTED_RESOURCE_TYPES)
    schedulers = sa.Enum(*const.DB_SUPPORTED_SCHEDULERS)
    forward_methods = sa.Enum(*const.SUPPORTED_FORWARD_METHODS)

    # create table ipvs_revisions in context engine sqlite://
    metadata = sa.MetaData()
    sa.Table('ipvs_loadbalancers', metadata,
             sa.Column('tenant_id', sa.String(255), nullable=False),
             sa.Column('id', sa.String(36), nullable=False, primary_key=True),
             sa.Column('name', sa.String(255), nullable=True),
             sa.Column('description', sa.String(255), nullable=True),
             sa.Column('admin_state_up', sa.Boolean(), nullable=False),
             )
    sa.Table('ipvs_virtualservers', metadata,
             sa.Column('tenant_id', sa.String(255), nullable=False),
             sa.Column('id', sa.String(36), nullable=False, primary_key=True),
             sa.Column('name', sa.String(255), nullable=True),
             sa.Column('listen_ip', sa.String(64), nullable=False),
             sa.Column('listen_port', sa.Integer(), nullable=False),
             sa.Column('ipvs_loadbalancer_id', sa.String(36), nullable=False),
             sa.Column('admin_state_up', sa.Boolean(), nullable=False),
             sa.ForeignKeyConstraint(['ipvs_loadbalancer_id'],
                                     ['ipvs_loadbalancers.id'],
                                     ondelete='CASCADE'),
             sa.Column('neutron_network_id', sa.String(36), nullable=False),
             sa.Column('neutron_port_id', sa.String(36), nullable=False),
             sa.Column('scheduler', schedulers, nullable=False),
             sa.Column('forward_method', forward_methods, nullable=False),
             sa.UniqueConstraint('listen_ip', 'listen_port',
                                 'neutron_network_id'),
             )
    sa.Table('ipvs_realservers', metadata,
             sa.Column('tenant_id', sa.String(255), nullable=False),
             sa.Column('id', sa.String(36), nullable=False, primary_key=True),
             sa.Column('name', sa.String(255), nullable=True),
             sa.Column('server_ip', sa.String(64), nullable=False),
             sa.Column('server_port', sa.Integer(), nullable=False),
             sa.Column('weight', sa.Integer(), nullable=False),
             sa.Column('delay', sa.Integer(), nullable=False),
             sa.Column('timeout', sa.Integer(), nullable=False),
             sa.Column('max_retries', sa.Integer(), nullable=False),
             sa.Column('admin_state_up', sa.Boolean(), nullable=False),
             sa.Column('ipvs_virtualserver_id', sa.String(36), nullable=False),
             sa.ForeignKeyConstraint(['ipvs_virtualserver_id'],
                                     ['ipvs_virtualservers.id'],
                                     ondelete='CASCADE'),
             sa.UniqueConstraint('server_ip', 'server_port',
                                 'ipvs_virtualserver_id'),
             )
    sa.Table('ipvs_revisions', metadata,
             sa.Column('id', sa.String(36), primary_key=True),
             sa.Column('resource_type', resource_types, nullable=False),
             sa.Column('parent_id', sa.String(36)),
             sa.Column('created_at', sa.DateTime(), nullable=True),
             sa.Column('updated_at', sa.DateTime(), nullable=True),
             sa.Column('deleted_at', sa.DateTime(), nullable=True),
             sa.Column('extra', sa.String(128)))
    sa.Table('ipvs_quotas', metadata,
             sa.Column('tenant_id', sa.String(36), primary_key=True),
             sa.Column('quota_type', resource_types, primary_key=True),
             sa.Column('quota', sa.Integer(), nullable=False))
    metadata.create_all(context.session.get_bind())
    return context


def lb_create_body(tenant_id, up=True):
    return {
        const.IPVS_LOADBALANCER: {
            'tenant_id': tenant_id,
            'name': '',
            'description': '',
            const.ADMIN_STATE_UP: up}
        }


def lb_update_body():
    return {const.IPVS_LOADBALANCER: {}}


def update_name(d, name):
    d.values()[0]['name'] = name


def pop_update_name(d):
    d.values()[0].pop('name', None)


def pop_update_admin_state(d):
    d.values()[0].pop(const.ADMIN_STATE_UP, None)


def update_up(d):
    d.values()[0][const.ADMIN_STATE_UP] = True


def update_down(d):
    d.values()[0][const.ADMIN_STATE_UP] = False


def update_attr(d, k, v):
    d.values()[0][k] = v


def vs_create_body(tenant_id, lb_id, net_id, lip, lport, sche=const.SOURCE_IP,
                   fwrd=const.DR, up=True):
    return {
        const.IPVS_VIRTUALSERVER: {
            'tenant_id': tenant_id,
            'name': '',
            const.LISTEN_IP: lip,
            const.LISTEN_PORT: lport,
            'neutron_network_id': net_id,
            const.ADMIN_STATE_UP: up,
            const.SCHEDULER: sche,
            const.FORWARD_METHOD: fwrd,
            'ipvs_loadbalancer_id': lb_id}
        }


def vs_update_body():
    return {const.IPVS_VIRTUALSERVER: {}}


def rs_create_body(tenant_id, vs_id, sip, sport, w=1, d=3, t=3, r=3, up=True):
    return {
        const.IPVS_REALSERVER: {
             'tenant_id': tenant_id,
             'name': '',
             const.SERVER_IP: sip,
             const.SERVER_PORT: sport,
             const.WEIGHT: w,
             const.DELAY: d,
             const.TIMEOUT: t,
             const.MAX_RETRIES: r,
             const.ADMIN_STATE_UP: up,
             'ipvs_virtualserver_id': vs_id}
        }


def rs_update_body():
    return {const.IPVS_REALSERVER: {}}


def quota_create_body(tenant_id, quota_type, quota, target_tenant=None):
    return {
        const.IPVS_QUOTA: {
            'tenant_id': tenant_id,
            const.QUOTA_TYPE: quota_type,
            const.TARGET_TENANT: target_tenant,
            const.QUOTA: quota}
    }


def assert_notify_none(case_msg):
    assert_helper.assert_true(len(notifications) == 0, case_msg)


def assert_notified(notifications, idx, expected_meth, expected_data,
                    case_msg):
    failed_msg = case_msg + "...failed"
    try:
        if idx < 0:
            assert len(notifications) >= abs(idx)
        else:
            assert len(notifications) >= idx + 1
    except AssertionError:
        print failed_msg
        print "notifications has no item in position %s" % idx
        os.sys.exit(1)
    else:
        notify_meth, notfiy_body = notifications[idx]
        try:
            assert notify_meth == expected_meth
        except AssertionError:
            print failed_msg
            print notify_meth, "!=", expected_meth
            os.sys.exit(1)
        else:
            assert_helper.assert_dict_equals(notfiy_body, expected_data,
                                             case_msg)


def assert_revision(func, created_at, updated_at, deleted_at, extra, case_msg,
                    *args):
    failed_msg = case_msg + "...failed"
    rev = func(*args)
    for (ob, ep, at) in ((rev.created_at, created_at, 'create_at'),
                         (rev.updated_at, updated_at, 'update_at'),
                         (rev.deleted_at, deleted_at, 'delete_at')):
        try:
            if ep is None:
                assert ob == ep
            else:
                if ep == 0:
                    ep = datetime.datetime.utcnow()
                assert (ep - ob).seconds < 1
        except AssertionError:
            print failed_msg
            print "revision timestamp %s not match" % at
            os.sys.exit(1)
    assert_helper.assert_equals(rev.extra, extra, case_msg)
