import re
import requests

from datetime import datetime

from requests.auth import AuthBase
from urllib3.util import Retry
from bs4 import BeautifulSoup

from spacer import models


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
    persist=True
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

    def __init__(self, results, entity_class, params):
        self.content = results.content
        self.url = results.url
        self.entity_class = entity_class
        self.params = params

    def _parse_datetime_post(self, dt_str):
        date_format = '%b %d, %Y at %I:%M %p'
        return datetime.strptime(dt_str, date_format)
    
    def _parse_datetime_user(self, dt_str):
        date_format = '%b %d, %Y'
        return datetime.strptime(dt_str, date_format)
    
    def _count_likes(self, reactions):
        match = re.match(r'^(.*?)(?:\s+and\s+(.+))?$', reactions)
        x = len(match.group(1).split(','))
        y = 0
        if match.group(2):
            match2 = re.match('^([0-9]+) others', match.group(2))
            y = int(match2.group(1)) if match2 else 1
        return x + y
    
    def _clean_text(self, text):
        clean_text = text.replace('\n', '')
        return clean_text
        
    def _extract_user_data_from_message(self, message):
        user_meta1 = message.find('div', class_="message-userDetails")
        user_meta2 = user_meta1.find('a', class_='username')
        id = user_meta2['data-user-id']
        username = user_meta2.text
        role = ', '.join([t.text for t in user_meta1.select('[itemprop="jobTitle"]')])

        user_data1 = message.find('div', class_='message-userExtras')
        user_data2 = user_data1.find_all('dd')
        join_date = self._parse_datetime_user(user_data2[0].text)
        messages = user_data2[1].text
        reaction_score = user_data2[2].text
        points = user_data2[3].text

        user_data = {
            'id': id,
            'username': username,
            'role': role,
            'join_date': join_date,
            'messages': messages,
            'reaction_score': reaction_score,
            'points': points
        }

        return user_data

    def _extract_posts_and_users(self, soup):
        messages = soup.find_all("div", class_="message-inner")
        posts = []
        users = []
        for message in messages:

            user = self._extract_user_data_from_message(message)

            post_box = message.find("div", class_="message-userContent lbContainer js-lbContainer")

            id = post_box['data-lb-id'].split('-')[1]
            meta = post_box['data-lb-caption-desc'].split(' · ')
            post_text = post_box.text

            reactions = message.find('a', class_="reactionsBar-link")

            post = {
                'id': id,
                'user_id': user['id'],
                'username': meta[0],
                'thread': self.params['title'],
                'message': self._clean_text(post_text),
                'likes': self._count_likes(reactions.text) if reactions else 0,
                'time_posted': self._parse_datetime_post(meta[1]),
            }
            posts.append(post)
            users.append(user)
        return posts, users
    
    def _extract_threads(self, soup):
        tags = soup.find_all("div", class_="structItem-title")
        threads = [tag['uix-href'].split('/')[-2] for tag in tags]
        return threads

    def extract(self):
        soup =  BeautifulSoup(self.content, "html.parser")
        if self.entity_class == 'posts':
            posts, users = self._extract_posts_and_users(soup)
            if config.persist:
                for post, user in zip(posts, users):
                    models.Post.create_or_update(**post)
                    models.User.create_or_update(**user)
            return posts, users
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
        return Results(results, self.__class__.__name__.lower(), self.params)

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
