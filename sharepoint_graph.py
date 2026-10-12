"""Microsoft Graph transport. Credentials stay in environment/Streamlit Secrets."""
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import msal
import requests


class GraphError(RuntimeError):
    def __init__(self, status, code='GraphError'):
        self.status = status
        self.code = code
        super().__init__(f'Microsoft Graph: HTTP {status} ({code}).')


def setting(name, default=''):
    if name in os.environ:
        return os.environ[name]
    config = os.environ.get('ALTIVIA_CONFIG')
    if config:
        return json.loads(Path(config).read_text(encoding='utf-8')).get(name, default)
    try:
        import streamlit as st
        return st.secrets.get(name, default)
    except (ImportError, FileNotFoundError):
        return default


class Graph:
    base = 'https://graph.microsoft.com/v1.0'

    def __init__(self, token_provider=None, session=None):
        self.session = session or requests.Session()
        if token_provider:
            self.token_provider = token_provider
            return
        tenant = setting('SP_TENANT_ID')
        client = setting('SP_CLIENT_ID')
        key = setting('SP_PRIVATE_KEY')
        key_file = setting('SP_PRIVATE_KEY_FILE')
        if key_file:
            key = Path(key_file).read_text(encoding='utf-8')
        secret = setting('SP_CLIENT_SECRET')
        if not tenant or not client or not (key or secret):
            raise RuntimeError('Falta configurar la conexión privada de SharePoint.')
        credential = {'private_key': key, 'thumbprint': setting('SP_CERT_THUMBPRINT')} if key else secret
        self.app = msal.ConfidentialClientApplication(
            client, authority=f'https://login.microsoftonline.com/{tenant}',
            client_credential=credential)
        self.token_provider = self._token

    def _token(self):
        result = self.app.acquire_token_for_client(scopes=['https://graph.microsoft.com/.default'])
        if 'access_token' not in result:
            # Never echo authority responses, credentials or token contents into the UI.
            raise RuntimeError('No se pudo autenticar la aplicación en Microsoft Entra. Revisar credencial y consentimiento.')
        return result['access_token']

    def request(self, method, path, body=None, headers=None):
        url = path if path.startswith('https://') else self.base + '/' + path.lstrip('/')
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.netloc != 'graph.microsoft.com' or not parsed.path.startswith('/v1.0/'):
            raise ValueError('Destino Graph no autorizado.')
        for attempt in range(5):
            auth = {'Authorization': 'Bearer ' + self.token_provider(), 'Accept': 'application/json'}
            auth.update(headers or {})
            try:
                response = self.session.request(method, url, json=body, headers=auth,
                                                timeout=(10, 60), allow_redirects=False)
            except requests.RequestException:
                # Unknown write outcome: callers reconcile by unique key / committed ancestry.
                raise GraphError(0, 'ConnectionInterrupted') from None
            if response.status_code == 429 or (method == 'GET' and response.status_code in (502, 503, 504)):
                if attempt < 4:
                    delay = response.headers.get('Retry-After', '')
                    time.sleep(min(30, int(delay) if delay.isdigit() else 2 ** attempt))
                    continue
            if not 200 <= response.status_code < 300:
                try:
                    code = response.json().get('error', {}).get('code', 'GraphError')
                except ValueError:
                    code = 'GraphError'
                raise GraphError(response.status_code, code)
            return response.json() if response.content else {}
        raise GraphError(429, 'TooManyRequests')

    def pages(self, path):
        while path:
            data = self.request('GET', path)
            yield from data.get('value', [])
            path = data.get('@odata.nextLink')


def resolve_site(graph):
    site_id = setting('SP_SITE_ID')
    if site_id:
        return site_id
    host = setting('SP_HOSTNAME')
    path = setting('SP_SITE_PATH')
    if not host.endswith('.sharepoint.com') or not path.startswith('/sites/'):
        raise RuntimeError('Configura SP_SITE_ID o SP_HOSTNAME y SP_SITE_PATH.')
    return graph.request('GET', f'/sites/{host}:{path}')['id']
