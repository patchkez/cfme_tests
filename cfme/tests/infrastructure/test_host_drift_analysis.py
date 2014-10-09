# -*- coding: utf-8 -*-

from cfme.fixtures import pytest_selenium as sel
from cfme.infrastructure import host
from cfme.web_ui import flash
from utils import conf
from utils import testgen
from utils.wait import wait_for
import pytest

pytestmark = [pytest.mark.usefixtures("setup_infrastructure_providers")]


def pytest_generate_tests(metafunc):
    p_argn, p_argv, p_ids = testgen.infra_providers(metafunc, 'hosts')
    argnames = ['provider_key', 'host_type', 'host_name']
    argvalues = []
    idlist = []
    for argv in p_argv:
        prov_hosts, prov_key = argv[0], argv[1]
        if not prov_hosts:
            continue
        for test_host in prov_hosts:
            if not test_host.get('test_fleece', False):
                continue

            argvalues.append([prov_key, test_host['type'], test_host['name']])
            test_id = '{}-{}-{}'.format(prov_key, test_host['type'], test_host['name'])
            idlist.append(test_id)

    metafunc.parametrize(argnames, argvalues, ids=idlist, scope="module")


def get_host_data_by_name(provider_key, host_name):
    for host_obj in conf.cfme_data['management_systems'][provider_key].get('hosts', []):
        if host_name == host_obj['name']:
            return host_obj
    return None


def test_host_drift_analysis(request, provider_key, host_type, host_name):
    host_data = get_host_data_by_name(provider_key, host_name)
    test_host = host.Host(name=host_name)

    wait_for(lambda: test_host.exists, delay=10, num_sec=120, fail_func=sel.refresh)

    # get drift history num
    drift_num_orig = int(test_host.get_detail('Relationships', 'Drift History'))

    # add credentials to host + finalizer to remove them
    if not test_host.has_valid_credentials:
        test_host.update(
            updates={'credentials': host.get_credentials_from_config(host_data['credentials'])}
        )
        wait_for(
            lambda: test_host.has_valid_credentials,
            delay=10,
            num_sec=120,
            fail_func=sel.refresh
        )

        def test_host_remove_creds():
            test_host.update(
                updates={
                    'credentials': host.Host.Credential(
                        principal="",
                        secret="",
                        verify_secret=""
                    )
                }
            )
        request.addfinalizer(test_host_remove_creds)

    # initiate 1st analysis
    test_host.run_smartstate_analysis()
    flash.assert_message_contain('"{}": Analysis successfully initiated'.format(host_name))

    # wait for for drift history num+1
    wait_for(
        lambda: int(test_host.get_detail('Relationships', 'Drift History')) == drift_num_orig + 1,
        delay=20,
        num_sec=120,
        fail_func=sel.refresh
    )

    # change host name + finalizer to change it back
    orig_host_name = test_host.name
    test_host.update(
        updates={'name': '{}_tmp_drift_rename'.format(test_host.name)}
    )
    request.addfinalizer(
        lambda: test_host.update(updates={'name': orig_host_name})
    )

    # initiate 2nd analysis
    test_host.run_smartstate_analysis()
    flash.assert_message_contain('"{}": Analysis successfully initiated'.format(host_name))

    # wait for for drift history num+2
    wait_for(
        lambda: int(test_host.get_detail('Relationships', 'Drift History')) == drift_num_orig + 2,
        delay=20,
        num_sec=120,
        fail_func=sel.refresh
    )

    # check drift difference
    assert not test_host.are_drift_results_equal(0, 1)

    # click around the UI, do something funky
    # TODO
