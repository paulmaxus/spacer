import requests

from datetime import datetime

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
    

class Paginator:
    
    def __init__(self, entity_class, title, page=None, n_max=None):
        self.entity_class = entity_class
        self.title = title
        self.page = page
        self.n_max = n_max

        self._next_page = page

    def __iter__(self):
        self.n = 0
        return self

    def _is_max(self):
        if self.n_max and self.n >= self.n_max:
            return True
        return False

    def __next__(self):
        if self._next_page is None or self._is_max():
            raise StopIteration

        results = self.entity_class.get(self.title, self._next_page)

        # first page has no page endpoint
        if self._next_page == 1:
            returned_page = 1
        else:
            returned_page = int(results.url.split('-')[-1])
        if returned_page == self._next_page:
            self._next_page += 1
            return results
        else:
            # when page doesn't exist, last existing is shown: don't return
            raise StopIteration


class Results:
    """
    A class to hold and extract specific entities (posts or threads) from a webpage's HTML content.

    Attributes:
        content (str): The HTML content of the page to be parsed.
        url (str): The URL of the webpage.
        entity_class (str): Specifies whether to extract 'posts' or 'threads' from the page.
    """

    def __init__(self, results, entity_class):
        self.content = results.content
        self.url = results.url
        self.entity_class = entity_class

    def _parse_datetime(self, dt_str):
        date_format = '%b %d, %Y at %I:%M %p'
        return datetime.strptime(dt_str, date_format)

    def _extract_posts(self, soup):
        boxes = soup.find_all("div", class_="message-userContent lbContainer js-lbContainer")
        posts = []
        for box in boxes:
            meta = box['data-lb-caption-desc'].split(' · ')
            post = box.text
            posts.append(
                {
                    'user': meta[0],
                    'time': self._parse_datetime(meta[1]),
                    'post': post
                }
            )
        return posts
    
    def _extract_threads(self, soup):
        tags = soup.find_all("div", class_="structItem-title")
        threads = [tag['uix-href'].split('/')[-2] for tag in tags]
        return threads

    def extract(self):
        soup =  BeautifulSoup(self.content, "html.parser")
        if self.entity_class == 'posts':
            return self._extract_posts(soup)
        if self.entity_class == 'threads':
            return self._extract_threads(soup)
        else:
            return soup


class BaseSpacer:

    def __init__(self, params=None):
        self.params = params
        self.session = _get_requests_session()

    def _add_params(self, argument, new_params):
        if self.params is None:
            self.params = {argument: new_params}
        else:
            self.params[argument] = new_params

    @property
    def url(self):
        parent = 'threads'
        if self.__class__.__name__.lower() == 'posts':
            parent = 'threads'
        if self.__class__.__name__.lower() == 'threads':
            parent = 'forums'      
        url =  f'{config.space_url}/{parent}/{self.params["title"]}'
        if 'page' in self.params:
            url += '/page-' + str(self.params['page'])
        return url
        
    def _get_from_url(self, url):
        results = self.session.get(url, auth=SpacerAuth(config))
        results.raise_for_status()
        return Results(results, self.__class__.__name__.lower())

    def get(self, title, page=1):
        self._add_params("page", page)
        self._add_params("title", title)
        res = self._get_from_url(self.url)
        return res

    def paginate(self, title, page=1, n_max=10000):
        return Paginator(self, title=title, page=page, n_max=n_max)


class Posts(BaseSpacer):
    pass
    
class Threads(BaseSpacer):
    pass 