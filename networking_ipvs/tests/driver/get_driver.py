from networking_ipvs.tests.driver.keepalived import test_keepalived_driver


def driver(driver_name):
    def not_found():
        pass

    def keepalived():
        return test_keepalived_driver.IPVSDriver

    return {
        'keepalived': keepalived,
        }.get(driver_name, not_found)()
