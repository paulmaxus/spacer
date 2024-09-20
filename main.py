from spacer import config, Spacer


def main():

    config.max_retries = 0
    config.retry_backoff_factor = 0.1
    config.retry_http_codes = [429, 500, 503]

    spacer = Spacer()

    more_pages = True
    page_no = 1
    while more_pages:

        thread_name = 'nasas-perseverance-is-exploring-mars-come-watch-updates-with-us.37226'
        thread_url = f'https://forums.space.com/threads/{thread_name}/page-{page_no}'
        posts = spacer.get_posts(thread_url, page_no)
        page_no += 1