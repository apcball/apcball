"""External AI gateway transport; never invoked from computed fields or UI requests."""

import json

import requests


class GatewayError(Exception):
    """A retryable external gateway error."""


class GatewayTimeout(GatewayError):
    """The configured gateway timeout elapsed."""


class GatewayClient:
    """Send a gateway-neutral structured-analysis request."""

    def __init__(self, provider):
        self.provider = provider

    def invoke(self, analysis, system_instruction, user_prompt, output_schema):
        payload = {
            "analysis_id": analysis.id,
            "analysis_type": analysis.analysis_type,
            "provider_type": self.provider.provider_type,
            "model": self.provider.model_name,
            "system_instruction": system_instruction,
            "prompt": user_prompt,
            "output_schema": output_schema,
        }
        headers = {"Content-Type": "application/json"}
        api_key = self.provider._resolve_api_key()
        if api_key:
            headers["Authorization"] = "Bearer %s" % api_key
        try:
            response = requests.post(
                self.provider.base_url,
                data=json.dumps(payload),
                headers=headers,
                timeout=self.provider.timeout_seconds,
            )
            response.raise_for_status()
            response_payload = response.json()
        except requests.Timeout as error:
            raise GatewayTimeout("Gateway request timed out.") from error
        except (requests.RequestException, ValueError) as error:
            raise GatewayError(str(error)) from error
        if isinstance(response_payload, dict) and "structured_response" in response_payload:
            return response_payload["structured_response"]
        return response_payload
