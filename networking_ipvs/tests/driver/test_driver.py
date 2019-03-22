#!/usr/bin/python2.7

import copy

from oslo_utils import uuidutils

from networking_ipvs.common import constants as const
from networking_ipvs.common import rpc
from networking_ipvs.common import template
from networking_ipvs.drivers.keepalived import keepalived_driver
from networking_ipvs.drivers.keepalived import utils
import networking_ipvs.plugin
from networking_ipvs.tests.plugin import base
from networking_ipvs.tests.plugin import test_plugin as ptest


_NOTIFICATIONS = []


def wrapped_db_ops(func):
    def wrap(context, *args, **kwargs):
        res = func(context, *args, **kwargs)
        with context.session.begin():
            context.session.expire_all()
        return res
    return wrap


def fake_do_notify(*args, **kwargs):
    global _NOTIFICATIONS
    _NOTIFICATIONS.append((args[2], args[3]))


rpc.PluginMQNotifyMech._do_notify = fake_do_notify


class TestDriver(object):
    def __init__(self, driver_cls):
        tenant_id = uuidutils.generate_uuid()
        self.context = base.db_init()
        self.context.tenant_id = tenant_id
        self.plugin = networking_ipvs.plugin.NetworkingIPVSPlugin()
        self.plugin._db_create = wrapped_db_ops(self.plugin._db_create)
        self.plugin._db_update = wrapped_db_ops(self.plugin._db_update)
        self.plugin._db_delete = wrapped_db_ops(self.plugin._db_delete)
        self.plugin._update_revisions = wrapped_db_ops(
            self.plugin._update_revisions)
        self.driver = driver_cls(self.context, self.plugin)

    def run(self, single_test=None):
        def not_found():
            print "Single test %s not found" % single_test

        if single_test:
            single_test = single_test.replace(' ', '_')
            getattr(self, single_test, not_found)()
        else:
            for meth in dir(self):
                if meth.startswith('test_'):
                    getattr(self, meth)()

    def dispatch(func):
        def wrap(self, *args, **kwargs):
            global _NOTIFICATIONS
            for i in range(len(_NOTIFICATIONS)):
                _NOTIFICATIONS.pop()
            ret = func(self, *args, **kwargs)
            while _NOTIFICATIONS:
                method, data = _NOTIFICATIONS.pop(0)
                getattr(self.driver, method)(None, data)
            return ret
        return wrap

    def cleanup(func):
        def wrap(self, *args, **kwargs):
            ret = func(self, *args, **kwargs)
            for lb in self.plugin.get_ipvs_loadbalancers(self.context):
                self.plugin.delete_ipvs_loadbalancer(self.context, lb['id'],
                                                     body={'force': True})
            return ret
        return wrap

    def get_vs_keys_or_setdefault(self, vs):
        sche = vs.get(const.SCHEDULER, const.IPVS_SOURCE_HASHING)
        fwrd = vs.get(const.FORWARD_METHOD, const.DR)
        up = vs.get(const.ADMIN_STATE_UP, True)
        for k, v in ((const.SCHEDULER, sche), (const.FORWARD_METHOD, fwrd),
                     (const.ADMIN_STATE_UP, up)):
            vs.setdefault(k, v)
        return sche, fwrd, up

    def get_rs_keys_or_setdefault(self, rs):
        w = rs.get(const.WEIGHT, 1)
        d = rs.get(const.DELAY, 3)
        t = rs.get(const.TIMEOUT, 3)
        r = rs.get(const.MAX_RETRIES, 3)
        up = rs.get(const.ADMIN_STATE_UP, True)
        for k, v in ((const.WEIGHT, w), (const.DELAY, d), (const.TIMEOUT, t),
                     (const.MAX_RETRIES, r), (const.ADMIN_STATE_UP, up)):
            rs.setdefault(k, v)
        return w, d, t, r, up

    @dispatch
    def init_lb(self, lb_topo=None):
        if not lb_topo:
            lb_topo = self.get_init_lb_topo()
        lb = ptest.init_lb()
        for vs in lb_topo:
            sche, fwrd, up = self.get_vs_keys_or_setdefault(vs)
            sche = const.SCHEDULER_MAP.get(sche)
            _vs = ptest.init_vs(
                lb['id'], vs[const.LISTEN_IP], vs[const.LISTEN_PORT],
                sche=sche, fwrd=fwrd, up=up)
            vs[const.ID] = _vs['id']
            vs['lb_id'] = _vs['ipvs_loadbalancer_id']
            for rs in vs[const.REALSERVERS]:
                w, d, t, r, up = self.get_rs_keys_or_setdefault(rs)
                _rs = ptest.init_rs(
                    _vs['id'], rs[const.SERVER_IP], rs[const.SERVER_PORT],
                    w=w, d=d, t=t, r=r, up=up)
                rs[const.ID] = _rs['id']
        return lb_topo

    def get_init_lb_topo(self):
        return [
            {const.LISTEN_IP: '192.168.10.10',
             const.LISTEN_PORT: 8080,
             const.REALSERVERS: [
                 {const.SERVER_IP: '192.168.100.10',
                  const.SERVER_PORT: 8080},
                 {const.SERVER_IP: '192.168.100.11',
                  const.SERVER_PORT: 8080},
                 ],
             },
            {const.LISTEN_IP: '192.168.10.11',
             const.LISTEN_PORT: 8080,
             const.FORWARD_METHOD: const.NAT,
             const.SCHEDULER: const.IPVS_WEIGHTED_ROUND_ROBIN,
             const.REALSERVERS: [
                 {const.SERVER_IP: '192.168.100.12',
                  const.SERVER_PORT: 80},
                 {const.SERVER_IP: '192.168.100.13',
                  const.SERVER_PORT: 80},
                 ],
             },
        ]

    def get_rs_req(self, ip, port, w, d, t, r, up=None):
        ret = {}
        if ip:
            ret.update({const.SERVER_IP: ip, const.SERVER_PORT: port,
                        const.ADMIN_STATE_UP: True})
        for k, v in ((const.WEIGHT, w), (const.DELAY, d), (const.TIMEOUT, t),
                     (const.MAX_RETRIES, r), (const.ADMIN_STATE_UP, up)):
            if v is not None:
                ret[k] = v
        return ret

    def get_vs_req(self, sche=None, fwrd=None, up=None):
        ret = {}
        for k, v in ((const.SCHEDULER, sche), (const.FORWARD_METHOD, fwrd),
                     (const.ADMIN_STATE_UP, up)):
            if v is not None:
                ret[k] = v
        return ret

    def get_lb_req(self, up=None):
        ret = {}
        if up is not None:
            ret[const.ADMIN_STATE_UP] = up
        return ret

    @dispatch
    @cleanup
    def test_init(self):
        lb_info = self.init_lb()
        for vs_info in lb_info:
            all_rs = vs_info.get(const.REALSERVERS)
            self.driver.assert_init(vs_info, all_rs,
                                    ptest.task_msg("test init"))

    @dispatch
    def create_rs(self, vs_id, ip, port, w=None, d=None, t=None, r=None):
        rs = self.get_rs_req(ip, port, w=w, d=d, t=t, r=r)
        w, d, t, r, up = self.get_rs_keys_or_setdefault(rs)
        _rs = ptest.init_rs(vs_id, ip, port, w=w, d=d, t=t, r=r, up=up)
        rs[const.ID] = _rs['id']
        return rs

    @dispatch
    def update_rs(self, rs_id, w=None, d=None, t=None, r=None, up=None):
        rs = self.get_rs_req(None, None, w=w, d=d, t=t, r=r, up=up)
        self.plugin.update_ipvs_realserver(
            self.context, rs_id, {const.IPVS_REALSERVER: rs})

    @dispatch
    def update_vs(self, vs_id, sche=None, fwrd=None, up=None):
        vs = self.get_vs_req(sche=sche, fwrd=fwrd, up=up)
        self.plugin.update_ipvs_virtualserver(
            self.context, vs_id, {const.IPVS_VIRTUALSERVER: vs})

    @dispatch
    def update_lb(self, lb_id, up=None):
        lb = self.get_lb_req(up=up)
        self.plugin.update_ipvs_loadbalancer(
            self.context, lb_id, {const.IPVS_LOADBALANCER: lb})

    @dispatch
    def delete_rs(self, rs_id):
        self.plugin.delete_ipvs_realserver(self.context, rs_id)

    @dispatch
    def delete_vs(self, vs_id):
        self.plugin.delete_ipvs_virtualserver(self.context, vs_id,
                                              body={'force': True})

    @dispatch
    def delete_lb(self, lb_id):
        self.plugin.delete_ipvs_loadbalancer(self.context, lb_id,
                                             body={'force': True})

    @dispatch
    @cleanup
    def test_create_rs(self):
        lb = self.init_lb()
        vs_info = lb[1]
        all_rs = vs_info.get(const.REALSERVERS)
        rs = self.create_rs(vs_info['id'], '192.168.100.14', 80)
        all_rs.append(rs)
        self.driver.assert_create_rs(vs_info, all_rs,
                                     ptest.task_msg("test create rs"))

    @dispatch
    @cleanup
    def test_update_rs(self):
        lb = self.init_lb()
        vs_info = lb[1]
        all_rs = vs_info.get(const.REALSERVERS)
        self.update_rs(all_rs[0]['id'], w=123, d=123)
        all_rs[0][const.WEIGHT] = 123
        all_rs[0][const.DELAY] = 123
        self.driver.assert_update_rs(vs_info, all_rs,
                                     ptest.task_msg("test update rs"))

    @dispatch
    @cleanup
    def test_update_rs_down(self):
        lb = self.init_lb()
        vs_info = lb[1]
        all_rs = vs_info.get(const.REALSERVERS)
        self.update_rs(all_rs[0]['id'], up=False)
        all_rs[0][const.ADMIN_STATE_UP] = False
        self.driver.assert_update_rs_down(
            vs_info, all_rs, ptest.task_msg("test update rs up(down)"))

    @dispatch
    @cleanup
    def test_update_rs_up(self):
        lb = self.init_lb()
        vs_info = lb[1]
        all_rs = vs_info.get(const.REALSERVERS)
        self.update_rs(all_rs[0]['id'], up=False)
        all_rs[0][const.ADMIN_STATE_UP] = False
        self.driver.assert_update_rs_down(
            vs_info, all_rs, ptest.task_msg("test update rs up(down)"))
        self.update_rs(all_rs[0]['id'], up=True)
        all_rs[0][const.ADMIN_STATE_UP] = True
        self.driver.assert_update_rs_up(
            vs_info, all_rs, ptest.task_msg("test update rs up(up)"))

    @dispatch
    @cleanup
    def test_delete_rs(self):
        lb = self.init_lb()
        vs_info = lb[1]
        all_rs = vs_info.get(const.REALSERVERS)
        rs = all_rs.pop(0)
        self.delete_rs(rs['id'])
        self.driver.assert_delete_rs(
            vs_info, all_rs, ptest.task_msg("test delete rs"))

    @dispatch
    @cleanup
    def test_update_vs(self):
        lb = self.init_lb()
        vs = lb[1]
        all_rs = vs.get(const.REALSERVERS)
        self.update_vs(vs['id'], sche=const.SOURCE_IP)
        vs[const.SCHEDULER] = const.IPVS_SOURCE_HASHING
        self.driver.assert_update_vs(
            vs, all_rs, ptest.task_msg("test update vs"))

    def turn_all(self, vs, up_or_down):
        vs[const.ADMIN_STATE_UP] = up_or_down
        for rs in vs[const.REALSERVERS]:
            rs[const.ADMIN_STATE_UP] = up_or_down

    @dispatch
    @cleanup
    def test_update_vs_down(self):
        lb = self.init_lb()
        vs = lb[1]
        all_rs = vs.get(const.REALSERVERS)
        self.update_vs(vs['id'], up=False)
        self.turn_all(vs, False)
        self.driver.assert_update_vs_down(
            vs, all_rs, ptest.task_msg("test update vs down"))

    @dispatch
    @cleanup
    def test_update_vs_up(self):
        lb = self.init_lb()
        vs = lb[1]
        all_rs = vs.get(const.REALSERVERS)
        self.update_vs(vs['id'], up=False)
        self.turn_all(vs, False)
        self.driver.assert_update_vs_down(
            vs, all_rs, ptest.task_msg("test update vs up(down)"))
        self.update_vs(vs['id'], up=True)
        self.turn_all(vs, True)
        self.driver.assert_update_vs_up(
            vs, all_rs, ptest.task_msg("test update vs up(up)"))

    @dispatch
    @cleanup
    def test_delete_vs(self):
        lb = self.init_lb()
        vs = lb[1]
        self.delete_vs(vs['id'])
        self.driver.assert_delete_vs(vs, ptest.task_msg("test delete vs"))

    @dispatch
    @cleanup
    def test_update_lb_down(self):
        lb = self.init_lb()
        self.update_lb(lb[0]['lb_id'], up=False)
        for i in range(len(lb)):
            vs = lb[i]
            vs[const.ADMIN_STATE_UP] = False
            self.turn_all(vs, False)
            self.driver.assert_update_vs_down(
                vs, vs[const.REALSERVERS],
                ptest.task_msg("test update lb down(vs %s)" % i))

    @dispatch
    @cleanup
    def test_update_lb_up(self):
        lb = self.init_lb()
        self.update_lb(lb[0]['lb_id'], up=False)
        for i in range(len(lb)):
            vs = lb[i]
            self.turn_all(vs, False)
            self.driver.assert_update_vs_down(
                vs, vs[const.REALSERVERS],
                ptest.task_msg("test update lb up(down vs %s)" % i))
        self.update_lb(lb[0]['lb_id'], up=True)
        for i in range(len(lb)):
            vs[const.ADMIN_STATE_UP] = True
            self.turn_all(vs, True)
            self.driver.assert_update_vs_up(
                vs, vs[const.REALSERVERS],
                ptest.task_msg("test update lb up(up vs %s)" % i))

    @dispatch
    @cleanup
    def test_delete_lb(self):
        lb = self.init_lb()
        self.delete_lb(lb[0]['lb_id'])
        for i in range(len(lb)):
            self.driver.assert_delete_vs(
                lb[i], ptest.task_msg("test delete lb(vs %s)" % i))

    @dispatch
    @cleanup
    def test_update_subresource_changed_during_lb_down(self):
        lb = self.init_lb()
        self.update_lb(lb[0]['lb_id'], up=False)
        for i in range(len(lb)):
            vs = lb[i]
            self.turn_all(vs, False)
            self.driver.assert_update_vs_down(
                vs, vs[const.REALSERVERS],
                ptest.task_msg("test update subresource during lb down"
                               "(down vs %s)" % i))
        rs = self.create_rs(lb[0]['id'], '192.168.100.14', 80)
        lb[0][const.REALSERVERS].append(rs)
        self.update_vs(lb[1]['id'], sche=const.SOURCE_IP)
        lb[1][const.SCHEDULER] = const.IPVS_SOURCE_HASHING
        self.update_rs(lb[1][const.REALSERVERS][0]['id'], w=123, d=123)
        lb[1][const.REALSERVERS][0].update(
            {const.WEIGHT: 123, const.DELAY: 123})
        self.update_lb(lb[0]['lb_id'], up=True)
        for i in range(len(lb)):
            vs[const.ADMIN_STATE_UP] = True
            self.turn_all(vs, True)
            self.driver.assert_update_vs_up(
                vs, vs[const.REALSERVERS],
                ptest.task_msg("test update subresource changed during lb down"
                               "(up vs %s)" % i))

    @dispatch
    @cleanup
    def test_update_subresource_changed_during_vs_down(self):
        lb = self.init_lb()
        vs = lb[1]
        all_rs = vs.get(const.REALSERVERS)
        self.update_vs(vs['id'], up=False)
        self.turn_all(vs, False)
        self.driver.assert_update_vs_down(
            vs, all_rs, ptest.task_msg(
                "test update subresource changed during vs down(down)"))
        self.update_vs(vs['id'], sche=const.SOURCE_IP)
        vs[const.SCHEDULER] = const.IPVS_SOURCE_HASHING
        self.update_rs(vs[const.REALSERVERS][0]['id'], w=123, d=123)
        vs[const.REALSERVERS][0].update(
            {const.WEIGHT: 123, const.DELAY: 123})
        rs = self.create_rs(vs['id'], '192.168.100.14', 80)
        vs[const.REALSERVERS].append(rs)
        self.update_vs(vs['id'], up=True)
        self.turn_all(vs, True)
        self.driver.assert_update_vs_up(
            vs, all_rs, ptest.task_msg(
                "test update subresource changed during vs down(up)"))
