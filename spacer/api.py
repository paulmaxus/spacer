import re
import requests

from datetime import datetime

from requests.auth import AuthBase
from urllib3.util import Retry
from bs4 import BeautifulSoup

from spacer import models


class SpacerConfig(dict):
    """
    Configuration class that extends dict to allow attribute-style access to configuration settings.

    Example:
        config = SpacerConfig(user_agent="spacer")
        print(config.user_agent)  # Accessed as attribute
        print(config["user_agent"])  # Accessed as dictionary
    """

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
    persist=True,
)


def _get_requests_session():
    """
    Creates and configures a requests Session with automatic retry capabilities.

    Returns:
        requests.Session: Configured session object with retry settings.
    """
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
    """
    Authentication handler for requests to space.com forums.

    Args:
        config (SpacerConfig): Configuration instance containing auth settings.
    """

    def __init__(self, config):
        self.config = config

    def __call__(self, r):
        """
        Modifies the request headers to include authentication information.

        Args:
            r (requests.Request): The request to be modified.

        Returns:
            requests.Request: Modified request with authentication headers.
        """
        if self.config.user_agent:
            r.headers["User-Agent"] = self.config.user_agent

        return r


class Paginator:
    """
    Handles pagination of forum content, allowing iteration over multiple pages of results.

    Args:
        entity_class: Class of entity to paginate (Posts or Threads)
        title (str): Title/identifier of the thread or forum
        page (int, optional): Starting page number. Defaults to None.
        n_max (int, optional): Maximum number of items to retrieve. Defaults to None.
    """

    def __init__(self, entity_class, title, page=None, n_max=None):
        self.entity_class = entity_class
        self.title = title
        self.page = page
        self.n_max = n_max

        self._next_page = page
        self._previous_url = ""

    def __iter__(self):
        """Initializes the iterator."""
        self.n = 0
        return self

    def _is_max(self):
        """
        Checks if the maximum number of items has been reached.

        Returns:
            bool: True if maximum reached, False otherwise.
        """
        if self.n_max and self.n >= self.n_max:
            return True
        return False

    def __next__(self):
        """
        Returns the next page of results.

        Returns:
            Results: Next page of results.

        Raises:
            StopIteration: When no more pages are available or maximum items reached.
        """
        if self._next_page is None or self._is_max():
            raise StopIteration

        results = self.entity_class.get(self.title, self._next_page)

        if self._previous_url != results.url:
            self._next_page += 1
            self._previous_url = results.url
            return results
        else:
            raise StopIteration


class Results:
    """
    Parses and extracts specific entities (posts or threads) from webpage HTML content.

    Args:
        results (requests.Response): Response object from HTTP request
        entity_class (str): Type of entity to extract ('posts' or 'threads')
        params (dict): Additional parameters for extraction
    """

    def __init__(self, results, entity_class, params):
        self.content = results.content
        self.url = results.url
        self.entity_class = entity_class
        self.params = params

    def _parse_datetime_post(self, dt_str):
        """
        Parses post timestamps into datetime objects.

        Args:
            dt_str (str): DateTime string in format "MM DD, YYYY at HH:MM AM/PM"

        Returns:
            datetime: Parsed datetime object
        """
        date_format = "%b %d, %Y at %I:%M %p"
        return datetime.strptime(dt_str, date_format)

    def _parse_datetime_user(self, dt_str):
        """
        Parses user join dates into datetime objects.

        Args:
            dt_str (str): DateTime string in format "MM DD, YYYY"

        Returns:
            datetime: Parsed datetime object
        """
        date_format = "%b %d, %Y"
        return datetime.strptime(dt_str, date_format)

    def _count_likes(self, reactions):
        """
        Counts total reactions/likes from reaction string.

        Args:
            reactions (str): String containing reaction information

        Returns:
            int: Total number of reactions
        """
        match = re.match(r"^(.*?)(?:\s+and\s+(.+))?$", reactions)
        x = len(match.group(1).split(","))
        y = 0
        if match.group(2):
            match2 = re.match("^([0-9]+) others", match.group(2))
            y = int(match2.group(1)) if match2 else 1
        return x + y

    def _clean_text(self, text):
        """
        Sanitizes text content by removing excess whitespace.
        Includes tabs and newlines.

        Args:
            text (str): Raw text content

        Returns:
            str: Cleaned text
        """
        clean_text = re.sub(r"\s+", " ", text)
        return clean_text.strip()

    def _clean_number(self, number_string):
        """
        Converts string numbers to integers, removing commas.

        Args:
            number_string (str): Number as string

        Returns:
            int: Cleaned integer value
        """
        return int(number_string.replace(",", ""))

    def _extract_user_data_from_message(self, message):
        """
        Extracts user metadata from message HTML.

        Args:
            message (bs4.element.Tag): BeautifulSoup tag containing user data

        Returns:
            dict: Dictionary containing user metadata
        """
        user_meta1 = message.find("div", class_="message-userDetails")
        user_meta2 = user_meta1.find("a", class_="username")
        id = user_meta2["data-user-id"]
        username = user_meta2.text
        role = ", ".join([t.text for t in user_meta1.select('[itemprop="jobTitle"]')])

        user_data1 = message.find("div", class_="message-userExtras")
        user_data2 = user_data1.find_all("dd")
        join_date = self._parse_datetime_user(user_data2[0].text)
        messages = self._clean_number(user_data2[1].text)
        reaction_score = self._clean_number(user_data2[2].text)
        points = self._clean_number(user_data2[3].text)

        user_data = {
            "id": id,
            "username": username,
            "role": role,
            "join_date": join_date,
            "messages": messages,
            "reaction_score": reaction_score,
            "points": points,
        }

        return user_data

    def _extract_posts_and_users(self, soup):
        """
        Extracts post content and user data from page HTML.

        Args:
            soup (bs4.BeautifulSoup): Parsed HTML content

        Returns:
            tuple: List of posts and list of users
        """
        messages = soup.find_all("div", class_="message-inner")
        posts = []
        users = []
        for message in messages:
            user = self._extract_user_data_from_message(message)

            post_box = message.find(
                "div", class_="message-userContent lbContainer js-lbContainer"
            )

            id = post_box["data-lb-id"].split("-")[1]
            meta = post_box["data-lb-caption-desc"].split(" · ")

            post_body = post_box.find("div", class_="bbWrapper")
            post_text = " ".join(
                [
                    (e if not e.name else (e.text if e.name != "blockquote" else ""))
                    for e in post_body
                ]
            )
            reactions = message.find("a", class_="reactionsBar-link")

            post = {
                "id": id,
                "user_id": user["id"],
                "username": meta[0],
                "thread": self.params["title"],
                "message": self._clean_text(post_text),
                "likes": self._count_likes(reactions.text) if reactions else 0,
                "time_posted": self._parse_datetime_post(meta[1]),
            }
            posts.append(post)
            users.append(user)
        return posts, users

    def _extract_threads(self, soup):
        """
        Extracts thread identifiers from page HTML.

        Args:
            soup (bs4.BeautifulSoup): Parsed HTML content

        Returns:
            list: List of thread identifiers
        """
        tags = soup.find_all("div", class_="structItem-title")
        threads = [tag["uix-href"].split("/")[-2] for tag in tags]
        return threads

    def extract(self):
        """
        Processes and returns extracted data based on entity type.

        Returns:
            Union[tuple, list]: Extracted posts and users, or thread list
        """
        soup = BeautifulSoup(self.content, "html.parser")
        if self.entity_class == "posts":
            posts, users = self._extract_posts_and_users(soup)
            if config.persist:
                for post, user in zip(posts, users):
                    models.Post.create_or_update(**post)
                    models.User.create_or_update(**user)
            return posts, users
        if self.entity_class == "threads":
            return self._extract_threads(soup)
        else:
            return soup


class BaseSpacer:
    """
    Base class for Posts and Threads classes, handling common functionality.

    Args:
        params (dict, optional): Dictionary of parameters for requests. Defaults to None.
    """

    def __init__(self, params=None):
        self.params = params
        self.session = _get_requests_session()

    def _add_params(self, argument, new_params):
        """
        Adds parameters to the request.

        Args:
            argument (str): Parameter key
            new_params: Parameter value
        """
        if self.params is None:
            self.params = {argument: new_params}
        else:
            self.params[argument] = new_params

    @property
    def url(self):
        """
        Builds the appropriate URL for requests.

        Returns:
            str: Complete URL for the request
        """
        parent = "threads"
        if self.__class__.__name__.lower() == "posts":
            parent = "threads"
        if self.__class__.__name__.lower() == "threads":
            parent = "forums"
        url = f'{config.space_url}/{parent}/{self.params["title"]}'
        if "page" in self.params:
            url += "/page-" + str(self.params["page"])
        return url

    def _get_from_url(self, url):
        """
        Makes HTTP request and returns Results object.

        Args:
            url (str): URL to request

        Returns:
            Results: Results object containing response data
        """
        results = self.session.get(url, auth=SpacerAuth(config))
        results.raise_for_status()
        return Results(results, self.__class__.__name__.lower(), self.params)

    def get(self, title, page=1):
        """
        Retrieves data for a specific title and page.

        Args:
            title (str): Title/identifier to retrieve
            page (int, optional): Page number. Defaults to 1.

        Returns:
            Results: Results object containing response data
        """
        self._add_params("page", page)
        self._add_params("title", title)
        res = self._get_from_url(self.url)
        return res

    def paginate(self, title, page=1, n_max=10000):
        """
        Creates a Paginator instance for multiple pages.

        Args:
            title (str): Title/identifier to paginate
            page (int, optional): Starting page number. Defaults to 1.
            n_max (int, optional): Maximum number of pages. Defaults to 10000.

        Returns:
            Paginator: Paginator instance
        """
        return Paginator(self, title=title, page=page, n_max=n_max)


class Posts(BaseSpacer):
    """
    Handler for forum posts. Inherits from BaseSpacer.
    Provides functionality to retrieve and process forum posts.
    """

    pass


class Threads(BaseSpacer):
    """
    Handler for forum threads. Inherits from BaseSpacer.
    Provides functionality to retrieve and process forum threads.
    """

    pass
