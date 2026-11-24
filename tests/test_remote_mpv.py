import http.client
import json
import threading
import unittest
from unittest import mock

import remote_mpv


class FakeHandler:
    def __init__(self, input_data=None, mpv_result="success"):
        self.input_data = input_data
        self.mpv_result = mpv_result
        self.commands = []
        self.success_data = None
        self.success_called = False

    def decode_json_input(self):
        return self.input_data

    def mpv_command(self, command):
        self.commands.append(command)
        return self.mpv_result

    def json_success(self, data=None):
        self.success_called = True
        self.success_data = data


class PropGetTest(unittest.TestCase):
    def test_get_loop_file(self):
        handler = FakeHandler(mpv_result="inf")

        remote_mpv.PropGet().get(handler, "loop-file")

        self.assertEqual(handler.commands, [["get_property", "loop-file"]])
        self.assertEqual(handler.success_data, {"loop-file": "inf"})


class PropSetTest(unittest.TestCase):
    def test_enable_loop_file(self):
        handler = FakeHandler({"loop-file": "inf"})

        remote_mpv.PropSet().post(handler)

        self.assertEqual(
            handler.commands,
            [["set_property", "loop-file", "inf"]],
        )
        self.assertTrue(handler.success_called)

    def test_disable_loop_file(self):
        handler = FakeHandler({"loop-file": "no"})

        remote_mpv.PropSet().post(handler)

        self.assertEqual(
            handler.commands,
            [["set_property", "loop-file", "no"]],
        )
        self.assertTrue(handler.success_called)

    def test_reject_invalid_loop_file_values(self):
        invalid_values = ("invalid", True, 1, None, [], {})

        for value in invalid_values:
            with self.subTest(value=value):
                handler = FakeHandler({"loop-file": value})

                with self.assertRaisesRegex(
                    remote_mpv.MpvNotAllowed,
                    "loop-file must be either 'inf' or 'no'",
                ):
                    remote_mpv.PropSet().post(handler)

                self.assertEqual(handler.commands, [])

    def test_reject_unallowed_property(self):
        handler = FakeHandler({"unallowed": "value"})

        with self.assertRaises(remote_mpv.MpvNotAllowed):
            remote_mpv.PropSet().post(handler)

        self.assertEqual(handler.commands, [])

    def test_existing_properties_keep_their_command_format(self):
        cases = (
            ({"pause": True}, ["set_property", "pause", True]),
            ({"speed": 1.5}, ["set_property", "speed", 1.5]),
            ({"volume": 50}, ["osd-msg-bar", "set", "volume", "50"]),
        )

        for input_data, expected_command in cases:
            with self.subTest(input_data=input_data):
                handler = FakeHandler(input_data)

                remote_mpv.PropSet().post(handler)

                self.assertEqual(handler.commands, [expected_command])


class MpvUnavailableTest(unittest.TestCase):
    def setUp(self):
        routes = [remote_mpv.PropGet(), remote_mpv.PropSet()]
        self.server = remote_mpv.MpvServer(
            "missing-mpv-socket",
            routes,
            ("127.0.0.1", 0),
        )
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, method, path, body=None):
        connection = http.client.HTTPConnection(*self.server.server_address)
        headers = {"Content-Type": "application/json"} if body else {}
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        response_body = json.loads(response.read())
        connection.close()
        return response.status, response_body

    def test_get_returns_500_when_mpv_is_unavailable(self):
        with self.unavailable_mpv_connections():
            status, response = self.request("GET", "/property/loop-file")

        self.assertEqual(status, 500)
        self.assertEqual(response, {"error": "Can't connect to mpv ipc server"})

    def test_post_returns_500_when_mpv_is_unavailable(self):
        with self.unavailable_mpv_connections():
            status, response = self.request(
                "POST",
                "/property",
                body=json.dumps({"loop-file": "inf"}),
            )

        self.assertEqual(status, 500)
        self.assertEqual(response, {"error": "Can't connect to mpv ipc server"})

    def unavailable_mpv_connections(self):
        return mock.patch.multiple(
            remote_mpv,
            NamedPipeConnection=mock.Mock(side_effect=FileNotFoundError),
            UnixSockConnection=mock.Mock(side_effect=FileNotFoundError),
        )


if __name__ == "__main__":
    unittest.main()
