import json
import os
import unittest
from datetime import UTC, datetime
from unittest.mock import Mock, patch

import httpx

from odwolania.extraction import DocumentExtractor
from odwolania.mistral import MistralClient, RateLimitError
from odwolania.templates import DocumentTemplate


EU_BASE = "https://api.eu.mistral.ai/v1"
CHAT = EU_BASE + "/chat/completions"
TRANSPORT = "httpx.HTTPTransport.handle_request"


def http_response(body, *, status=200, location=None):
    headers = {"Content-Type": "application/json"}
    if location:
        headers["Location"] = location
    return httpx.Response(status, headers=headers, content=body)


def reply(content, *, reason="stop"):
    return json.dumps({
        "id": "cmpl-test", "object": "chat.completion", "created": 1, "model": "model-from-env",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": reason}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }).encode()


class MistralIntegrationTest(unittest.TestCase):
    def setUp(self):
        env = {"MISTRAL_API_KEY": "mistral-test", "MISTRAL_MODEL": "model-from-env"}
        self.environment = patch.dict(os.environ, env, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_single_eu_request_preserves_document_and_only_sends_paths_of_local_fields(self):
        template = DocumentTemplate.parse("raport", '{// klient według rubryki\n"klient":"[PODMIOT]","numer":null}')
        document = "Raport\nKlient: [PODMIOT_1]\n\fNr: [NUMER_1]"
        mapping = {"[PODMIOT_1]": "Ukryty klient", "[NUMER_1]": "Numer wewnętrzny XYZ-876"}
        expected = {"klient": "[PODMIOT_1]", "numer": None}
        response = http_response(reply(json.dumps(expected)))
        with patch(TRANSPORT, return_value=response) as send:
            result = DocumentExtractor(MistralClient.from_environment()).extract_text(
                document, template, mapping, local_fields=(("numer",),),
            )
        self.assertEqual(result, expected)
        send.assert_called_once()
        req = send.call_args.args[-1]
        self.assertEqual(str(req.url), CHAT)
        self.assertEqual(req.method, "POST")
        self.assertEqual(req.headers["Authorization"], "Bearer mistral-test")
        body = json.loads(req.content)
        self.assertEqual(body["model"], "model-from-env")
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertEqual(body["temperature"], 0)
        self.assertEqual(body["top_p"], 1)
        system, user = body["messages"]
        self.assertEqual(system["role"], "system")
        self.assertIn(template.prompt, system["content"])
        self.assertIn('[["numer"]]', system["content"])
        self.assertEqual(user, {"role": "user", "content": document})
        for hidden in (*mapping.values(), "mistral-test"):
            self.assertNotIn(hidden, str(body))

    def test_lists_available_active_chat_models_with_a_single_get(self):
        body = {"object": "list", "data": [
            {"id": "z-chat", "type": "base", "capabilities": {"completion_chat": True}},
            {"id": "embedding", "type": "base", "capabilities": {"completion_chat": False}},
            {"id": "a-chat", "type": "fine-tuned", "job": "job-new", "root": "z-chat",
             "archived": False, "capabilities": {"completion_chat": True}},
            {"id": "old-chat", "type": "fine-tuned", "job": "job-old", "root": "z-chat",
             "archived": True, "capabilities": {"completion_chat": True}},
            {"id": "other", "type": "base", "capabilities": {}},
            {"id": "z-chat", "type": "base", "capabilities": {"completion_chat": True}},
        ]}
        url = EU_BASE + "/models"
        response = http_response(json.dumps(body).encode())
        with patch(TRANSPORT, return_value=response) as send:
            self.assertEqual(MistralClient.from_environment().list_models(), ["a-chat", "z-chat"])
        send.assert_called_once()
        req = send.call_args.args[-1]
        self.assertEqual(str(req.url), url)
        self.assertEqual(req.method, "GET")
        self.assertEqual(req.content, b"")

    def test_model_override_takes_priority_and_key_is_required(self):
        with patch(TRANSPORT, return_value=http_response(reply("{}"))) as send:
            self.assertEqual(MistralClient.from_environment(model="override").complete("{}", "raport"), "{}")
        req = send.call_args.args[-1]
        self.assertEqual(str(req.url), CHAT)
        self.assertEqual(json.loads(req.content)["model"], "override")
        self.assertEqual(req.headers["Authorization"], "Bearer mistral-test")
        del os.environ["MISTRAL_API_KEY"]
        with self.assertRaisesRegex(ValueError, "MISTRAL_API_KEY"):
            MistralClient.from_environment()

    def test_only_the_eu_endpoint_can_be_configured(self):
        for host in ("https://api.mistral.ai/v1", "https://api.us.mistral.ai/v1",
                     "http://api.eu.mistral.ai/v1", "https://other.example/v1",
                     EU_BASE + "?region=us"):
            with self.subTest(host=host), patch.dict(os.environ, MISTRAL_BASE_URL=host):
                with self.assertRaises(ValueError):
                    MistralClient.from_environment()
        for host in (EU_BASE + "/", "https://api.eu.mistral.ai:443/v1"):
            with self.subTest(host=host), patch.dict(os.environ, MISTRAL_BASE_URL=host):
                MistralClient.from_environment()

    def test_redirect_and_rate_limit_do_not_trigger_a_second_request(self):
        for status in (302, 429):
            with self.subTest(status=status):
                location = "https://other.example/chat/completions" if status == 302 else None
                response = http_response(b'{"message":"sensitive diagnostic"}', status=status, location=location)
                with patch(TRANSPORT, side_effect=[response]) as send:
                    with self.assertRaisesRegex(RuntimeError, f"HTTP {status}") as failure:
                        MistralClient.from_environment().complete("{}", "raport")
                self.assertNotIn("sensitive diagnostic", str(failure.exception))
                send.assert_called_once()

    def test_rate_limit_propagates_bounded_delay_without_replaying_the_request(self):
        now = datetime(2026, 11, 22, 8, 0, 0, 500_000, tzinfo=UTC)
        for header, delay in (
            (None, 60), ("n/a", 60), ("-2", 60), ("0", 0), ("27", 27), ("9" * 4500, 2700),
            ("Sun, 22 Nov 2026 08:00:12 GMT", 12), ("Sat, 21 Nov 2026 10:00:00 GMT", 0),
            ("Mon, 23 Nov 2026 08:00:00 GMT", 2700),
        ):
            with self.subTest(header=header):
                response = http_response(b'{"message":"diagnostic"}', status=429)
                if header is not None:
                    response.headers["Retry-After"] = header
                with patch(TRANSPORT, return_value=response) as send, patch("odwolania.mistral.datetime") as clock:
                    clock.now.return_value = now
                    with self.assertRaises(RateLimitError) as failure:
                        MistralClient.from_environment().complete("{}", "raport")
                self.assertEqual(failure.exception.retry_after, delay)
                self.assertNotIn("diagnostic", str(failure.exception))
                send.assert_called_once()

    def test_only_valid_token_counts_on_success_are_charged(self):
        client = MistralClient.from_environment()
        for cost, limit, status in (("1234", "100000", 200), (None, None, 200), ("0", "100", 200),
                                    ("abc", "100", 200), ("2", "-1", 200), ("1", "2", 429)):
            with self.subTest(cost=cost, limit=limit, status=status):
                callback = Mock()
                client.on_token_usage = callback
                response = http_response(reply("{}"), status=status)
                if cost is not None:
                    response.headers.update({"x-ratelimit-tokens-query-cost": cost, "x-ratelimit-limit-tokens-minute": limit})
                with patch(TRANSPORT, return_value=response) as send:
                    if status == 429:
                        with self.assertRaises(RateLimitError):
                            client.complete("{}", "raport")
                    else:
                        self.assertEqual(client.complete("{}", "raport"), "{}")
                if cost == "1234":
                    callback.assert_called_once_with(1234, 100000)
                else:
                    callback.assert_not_called()
                send.assert_called_once()

    def test_api_protocol_failures_surface_instead_of_producing_an_empty_extraction(self):
        template = DocumentTemplate.parse("raport", '{"nazwa": ""}')
        for payload in (
            b"invalid HTTP response body", b'{"choices":[]}', b'{"error":{"message":"error"}}',
            reply("{}", reason="tool_calls"),
            reply('{"nazwa":"niekompletne"}', reason="length"),
            reply(None), reply([{"type": "thinking", "thinking": [{"type": "text", "text": "ukryte rozumowanie"}]}]),
        ):
            with self.subTest(payload=payload):
                with patch(TRANSPORT, return_value=http_response(payload)) as send:
                    with self.assertRaises(RuntimeError):
                        DocumentExtractor(MistralClient.from_environment()).extract_text("raport", template, {})
                send.assert_called_once()

    def test_interrupted_http_body_is_reported_without_returning_partial_content(self):
        failure_at_transport = httpx.RemoteProtocolError("poufny-fragment")
        with patch(TRANSPORT, side_effect=failure_at_transport) as send:
            with self.assertRaises(RuntimeError) as failure:
                MistralClient.from_environment().complete("{}", "raport")
        self.assertNotIn("poufny-fragment", str(failure.exception))
        send.assert_called_once()

    def test_concatenates_only_text_chunks_in_multipart_answers(self):
        parts = [
            {"type": "thinking", "thinking": [{"type": "text", "text": "analiza"}]},
            {"type": "text", "text": '{"nazwa":'},
            {"type": "text", "text": '"test"}'},
        ]
        response = http_response(reply(parts))
        with patch(TRANSPORT, return_value=response) as send:
            self.assertEqual(MistralClient.from_environment().complete("{}", "raport"), '{"nazwa":"test"}')
        send.assert_called_once()

    def test_invalid_model_json_and_unrecognized_marker_are_recovered_locally(self):
        template = DocumentTemplate.parse("raport", '{"nazwa":"[PODMIOT]","kwota":0}')
        for content, expected in (
            ("niedomknięty {", {"nazwa": None, "kwota": None}),
            ('{"nazwa":"[PODMIOT_9]","kwota":17}', {"nazwa": None, "kwota": 17}),
        ):
            with self.subTest(content=content):
                response = http_response(reply(content))
                with patch(TRANSPORT, return_value=response) as send:
                    result = DocumentExtractor(MistralClient.from_environment()).extract_text(
                        "Kwota: 17 dla [PODMIOT_1]", template, {"[PODMIOT_1]": "Ukryta nazwa"},
                    )
                self.assertEqual(result, expected)
                send.assert_called_once()
