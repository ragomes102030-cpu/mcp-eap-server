"""Regression tests for the serverless public MCP response adapter."""
import asyncio
import unittest

from mcp_response_framing import buffer_json_response


class TestPublicResponseFraming(unittest.TestCase):
    def test_buffers_multiple_body_parts_and_replaces_transfer_framing(self):
        sent = []

        async def send(message):
            sent.append(message)

        async def exercise():
            buffered_send = buffer_json_response(send)
            await buffered_send({
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"transfer-encoding", b"chunked"),
                    (b"content-length", b"999"),
                ],
            })
            await buffered_send({
                "type": "http.response.body",
                "body": b'{"result":',
                "more_body": True,
            })
            await buffered_send({
                "type": "http.response.body",
                "body": b'"ok"}',
                "more_body": False,
            })

        asyncio.run(exercise())

        self.assertEqual(len(sent), 2)
        response_start, response_body = sent
        headers = dict(response_start["headers"])
        expected_body = b'{"result":"ok"}'
        self.assertEqual(response_start["status"], 200)
        self.assertNotIn(b"transfer-encoding", headers)
        self.assertEqual(headers[b"content-length"], str(len(expected_body)).encode())
        self.assertEqual(response_body["body"], expected_body)


if __name__ == "__main__":
    unittest.main()
