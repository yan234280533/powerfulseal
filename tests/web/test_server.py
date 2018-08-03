# Copyright 2018 Bloomberg Finance L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import json
from threading import Lock

import pkg_resources
import pytest
from mock import mock, MagicMock

from powerfulseal.k8s import Pod
from powerfulseal.node import Node, NodeState
from powerfulseal.policy import PolicyRunner
from powerfulseal.web import server


@pytest.fixture
def client():
    client = server.app.test_client()
    yield client


def test_get_policy_actions(client):
    server_state_mock = MagicMock()
    server_state_mock.get_policy = MagicMock(return_value={})
    with mock.patch("powerfulseal.web.server.server_state", server_state_mock):
        result = client.get("policy")
        assert json.loads(result.data) == {
            'config': [],
            'nodeScenarios': [],
            'podScenarios': []
        }


def test_put_policy_actions(client):
    server_state_mock = MagicMock()
    server_state_mock.update_policy = MagicMock()

    valid_policy_path = pkg_resources.resource_filename("tests.policy", "example_config.yml")
    valid_policy = PolicyRunner.load_file(valid_policy_path)

    invalid_policy = {
        'config': {
            'minSecondsBetweenRuns': 'invalid'
        }
    }

    with mock.patch("powerfulseal.web.server.server_state", server_state_mock):
        result = client.put("policy", data=json.dumps({
            'policy': valid_policy
        }), content_type='application/json')
        assert result.status_code == 200

        result = client.put("policy", data=json.dumps({
            'policy': invalid_policy
        }), content_type='application/json')
        assert result.status_code == 400


def test_get_logs(client):
    # An instance of Lock will have to be created as there is no straightforward
    # way to mock a lock
    server_state_mock = MagicMock()
    server_state_mock.lock = Lock()

    with mock.patch("powerfulseal.web.server.server_state", server_state_mock):
        # Test case where an offset is not specified
        server_state_mock.logs = [str(i) for i in range(3)]
        result = client.get("logs")
        assert json.loads(result.data)['logs'] == [str(i) for i in range(3)]

        # Test case where offset is specified and correct result is given
        server_state_mock.logs = [str(i) for i in range(9)]
        result = client.get("logs?offset=5")
        assert json.loads(result.data)['logs'] == ['5', '6', '7', '8']

        # Test edge case where just within range
        server_state_mock.logs = [str(i) for i in range(9)]
        result = client.get("logs?offset=8")
        assert json.loads(result.data)['logs'] == ['8']

        # Test edge case where just outside range
        server_state_mock.logs = [str(i) for i in range(9)]
        result = client.get("logs?offset=9")
        assert json.loads(result.data)['logs'] == []

        # Test case where offset is negative
        # Test edge case where just within range
        server_state_mock.logs = [str(i) for i in range(9)]
        result = client.get("logs?offset=-1")
        assert result.status_code == 400


def test_items(client):
    server_state_mock = MagicMock()

    test_node = Node(1, name='a',
                     ip='0.0.0.0',
                     az='A',
                     groups='a',
                     no=1,
                     state=NodeState.UP)
    server_state_mock.get_nodes = MagicMock(return_value=[test_node])

    test_pod = Pod('a',
                   namespace='a',
                   num=1,
                   uid='a',
                   host_ip='0.0.0.0',
                   ip='0.0.0.0',
                   container_ids=['a'],
                   state=0,
                   labels=['a'])
    server_state_mock.get_pods = MagicMock(return_value=[test_pod])

    with mock.patch("powerfulseal.web.server.server_state", server_state_mock):
        result = client.get('items')
        server_state_mock.get_nodes.assert_called_once()
        server_state_mock.get_pods.assert_called_once()

        data = json.loads(result.data)
        assert len(data['nodes']) == 1
        assert len(data['pods']) == 1

        # Ensure that the state is converted to an integer
        assert isinstance(data['nodes'][0]['state'], int)
        assert data['nodes'][0]['state'] == NodeState.UP


def test_update_nodes(client):
    server_state_mock = MagicMock()
    server_state_mock.start_node = MagicMock(return_value=True)
    server_state_mock.stop_node = MagicMock(return_value=True)

    test_node = Node(1, ip='0.0.0.0')
    server_state_mock.get_nodes = MagicMock(return_value=[test_node])

    with mock.patch("powerfulseal.web.server.server_state", server_state_mock):
        result = client.post('nodes', data=json.dumps({
            'action': 'start',
            'ip': '0.0.0.0'
        }), content_type='application/json')
        assert result.status_code == 200
        assert server_state_mock.start_node.call_count == 1
        assert server_state_mock.stop_node.call_count == 0

        result = client.post('nodes', data=json.dumps({
            'action': 'stop',
            'ip': '0.0.0.0'
        }), content_type='application/json')
        assert result.status_code == 200
        assert server_state_mock.start_node.call_count == 1
        assert server_state_mock.stop_node.call_count == 1


def test_update_pods(client):
    server_state_mock = MagicMock()

    test_pod = Pod('a', 'a', uid='1-1-1-1')
    server_state_mock.get_pods = MagicMock(return_value=[test_pod])
    server_state_mock.kill_pod = MagicMock(return_value=True)

    with mock.patch("powerfulseal.web.server.server_state", server_state_mock):
        result = client.post('pods', data=json.dumps({
            'is_forced': True,
            'uid': '1-1-1-1'
        }), content_type='application/json')
        assert result.status_code == 200
        server_state_mock.kill_pod.assert_called_once_with(test_pod, True)

        result = client.post('pods', data=json.dumps({
            'uid': '1-1-1-1'
        }), content_type='application/json')
        assert result.status_code == 200
        server_state_mock.kill_pod.assert_called_with(test_pod, False)

        result = client.post('pods', data=json.dumps({
            'is_forced': False,
            'uid': '1-1-1-1'
        }), content_type='application/json')
        assert result.status_code == 200
        server_state_mock.kill_pod.assert_called_with(test_pod, False)