# -*- coding: utf-8 -*-

import requests
import time
import json
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)


class BaseAPIClient:
    """Base HTTP client with throttling and logging"""
    
    def __init__(self, env):
        self.env = env
    
    def call(self, account, method, url, headers=None, body=None, timeout=30):
        """
        Make HTTP request with logging and retry logic
        
        Returns: (status_code, response_dict, error_message)
        """
        if headers is None:
            headers = {}
        
        start_time = datetime.now()
        status_code = 0
        response_body = {}
        error_message = None
        
        # Throttle API calls
        if account.api_call_delay > 0:
            time.sleep(account.api_call_delay)
        
        # Retry logic
        max_retries = account.api_max_retries
        retry_count = 0
        
        while retry_count <= max_retries:
            try:
                # Make request
                if method.upper() == 'GET':
                    response = requests.get(url, headers=headers, params=body, timeout=timeout)
                elif method.upper() == 'POST':
                    response = requests.post(url, headers=headers, json=body, timeout=timeout)
                elif method.upper() == 'PUT':
                    response = requests.put(url, headers=headers, json=body, timeout=timeout)
                else:
                    raise ValueError(f'Unsupported HTTP method: {method}')
                
                status_code = response.status_code
                
                # Try to parse JSON response
                try:
                    response_body = response.json()
                except:
                    response_body = {'text': response.text}
                
                # Handle rate limiting (HTTP 429)
                if status_code == 429:
                    retry_count += 1
                    if retry_count <= max_retries:
                        wait_time = account.api_call_delay * (2 ** retry_count)  # Exponential backoff
                        _logger.warning(f'Rate limited (429), retrying in {wait_time}s (attempt {retry_count}/{max_retries})')
                        time.sleep(wait_time)
                        continue
                    else:
                        error_message = 'Rate limit exceeded, max retries reached'
                        break
                
                # Success or non-retryable error
                if status_code >= 400:
                    error_message = response_body.get('message') or response_body.get('error') or f'HTTP {status_code}'
                
                break
                
            except requests.exceptions.Timeout:
                error_message = 'Request timeout'
                retry_count += 1
                if retry_count <= max_retries:
                    _logger.warning(f'Timeout, retrying (attempt {retry_count}/{max_retries})')
                    time.sleep(account.api_call_delay)
                    continue
                break
                
            except Exception as e:
                error_message = str(e)
                _logger.error(f'API call failed: {error_message}')
                break
        
        # Calculate duration
        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        
        # Mask secrets in headers for logging
        logged_headers = self._mask_secrets(headers)
        
        # Log to database
        try:
            self.env['buz.marketplace.api.log'].sudo().create({
                'account_id': account.id,
                'endpoint': url,
                'method': method,
                'request_headers': json.dumps(logged_headers, indent=2),
                'request_body': json.dumps(body, indent=2) if body else '',
                'response_status': status_code,
                'response_body': json.dumps(response_body, indent=2),
                'duration_ms': duration_ms,
                'error_message': error_message,
            })
        except Exception as e:
            _logger.error(f'Failed to log API call: {str(e)}')
        
        return status_code, response_body, error_message
    
    def _mask_secrets(self, headers):
        """Mask sensitive data in headers"""
        if not headers:
            return {}
        
        masked = headers.copy()
        sensitive_keys = ['authorization', 'api-key', 'x-api-key', 'partner-key', 'app-secret']
        
        for key in masked:
            if key.lower() in sensitive_keys:
                masked[key] = '***MASKED***'
        
        return masked
