#from urllib.parse import quote_plus

import requests
from requests.auth import AuthBase
from urllib3.util import Retry

from bs4 import BeautifulSoup


class SpacerConfig(dict):
    def __getattr__(self, key):
        return super().__getitem__(key)

    def __setattr__(self, key, value):
        return super().__setitem__(key, value)


config = SpacerConfig(
    user_agent="spacer",
    space_url="https://forums.space.com",
    max_retries=0,
    retry_backoff_factor=0.1,
    retry_http_codes=[429, 500, 503],
)


def _get_requests_session():
    # create a Requests Session with automatic retry:
    requests_session = requests.Session()
    retries = Retry(
        total=config.max_retries,
        backoff_factor=config.retry_backoff_factor,
        status_forcelist=config.retry_http_codes,
        allowed_methods={"GET"},
    )
    requests_session.mount(
        "https://", requests.adapters.HTTPAdapter(max_retries=retries)
    )

    return requests_session


class SpacerAuth(AuthBase):
    """auth class based on requests auth
    """

    def __init__(self, config):
        self.config = config

    def __call__(self, r):
        if self.config.user_agent:
            r.headers["User-Agent"] = self.config.user_agent

        return r



class Spacer:

    def __init__(self, params=None):
        self.params = params

    def _get_from_url(self, url, return_meta=False):
        res = _get_requests_session().get(url, auth=SpacerAuth(config))
        res.raise_for_status()
        soup = BeautifulSoup(res.content, "html.parser")
        return soup

    def get_posts(self, thread_name: str, page_no: int):
        url = f'{config.space_url}/threads/{thread_name}/page-{page_no}'
        return self._get_from_url(url)
