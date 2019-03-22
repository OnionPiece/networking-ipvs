from networking_ipvs.drivers.keepalived import keepalived_driver
from networking_ipvs.tests.driver.keepalived import base


class IPVSDriver(keepalived_driver.IPVSDriver):

    def __init__(self, context, plugin):
        conf = base.conf
        plugin_rpc = base.FakeRPC(context, plugin)
        base.cleanup()
        super(IPVSDriver, self).__init__(conf, plugin_rpc)

    def assert_init(self, vs_info, all_rs, task_msg):
        base.common_assert(vs_info, all_rs, task_msg)

    def assert_create_rs(self, vs_info, all_rs, task_msg):
        base.common_assert(vs_info, all_rs, task_msg)

    def assert_update_rs(self, vs_info, all_rs, task_msg):
        base.common_assert(vs_info, all_rs, task_msg)

    def assert_update_rs_down(self, vs_info, all_rs, task_msg):
        base.common_assert(vs_info, all_rs, task_msg)

    def assert_update_rs_up(self, vs_info, all_rs, task_msg):
        base.common_assert(vs_info, all_rs, task_msg)

    def assert_delete_rs(self, vs_info, all_rs, task_msg):
        base.common_assert(vs_info, all_rs, task_msg)

    def assert_update_vs(self, vs_info, all_rs, task_msg):
        base.common_assert(vs_info, all_rs, task_msg)

    def assert_update_vs_down(self, vs_info, all_rs, task_msg):
        base.common_assert(vs_info, all_rs, task_msg, vip_exists=False)

    def assert_update_vs_up(self, vs_info, all_rs, task_msg):
        base.common_assert(vs_info, all_rs, task_msg)

    def assert_delete_vs(self, vs_info, task_msg):
        base.common_assert(vs_info, [], task_msg, vip_exists=False)
