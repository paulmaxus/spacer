import pandas as pd
from peewee import *
from datetime import datetime
from typing import Union, List

# Database connection
db = SqliteDatabase("spacer.db")


class BaseModel(Model):
    """Base model class providing common functionality for all models."""

    class Meta:
        database = db

    @classmethod
    def create_or_update(cls, **kwargs):
        """
        Create a new record or update existing one based on ID.

        Args:
            **kwargs: Field values for the model instance

        Returns:
            None: The operation is executed directly on the database
        """
        current_time = datetime.now()
        kwargs["last_updated"] = current_time
        cls.insert(**kwargs).on_conflict(
            conflict_target=[cls.id], update=kwargs
        ).execute()


class User(BaseModel):
    """
    User model representing platform users.

    Attributes:
        id (int): Unique user identifier
        username (str): User's display name
        role (str): User's role in the system
        join_date (datetime): When the user joined
        messages (int): Count of user's messages
        reaction_score (int): Cumulative reaction score
        points (int): User's points in the system
        last_updated (datetime): Last record update timestamp
    """

    id = IntegerField(unique=True, primary_key=True)
    username = CharField(index=True)
    role = CharField()
    join_date = DateTimeField()
    messages = IntegerField(default=0)
    reaction_score = IntegerField(default=0)
    points = IntegerField(default=0)
    last_updated = DateTimeField()


class Post(BaseModel):
    """
    Post model representing user messages/posts.

    Attributes:
        id (int): Unique post identifier
        user_id (ForeignKeyField): Reference to the post author
        username (str): Username attached to post
        thread (str): Thread name
        message (str): Post content
        likes (int): Number of likes
        time_posted (datetime): When the post was created
        last_updated (datetime): Last record update timestamp
    """

    id = IntegerField(unique=True, primary_key=True)
    user_id = ForeignKeyField(User, backref="posts")
    username = CharField(index=True)
    thread = CharField(index=True)
    message = TextField()
    likes = IntegerField(default=0)
    time_posted = DateTimeField()
    last_updated = DateTimeField()


# Query functions with pandas integration
def get_posts_by_thread(
    thread: str, as_df: bool = True
) -> Union[List[Post], pd.DataFrame]:
    """
    Retrieve posts from a specific thread.

    Parameters
    ----------
    thread : str
        Thread identifier
    as_df : bool, optional
        If True, returns pandas DataFrame instead of query results
    """
    query = Post.select().where(Post.thread == thread)
    if as_df:
        return pd.DataFrame(query.dicts())
    return query


def get_all_posts(as_df: bool = True) -> Union[List[Post], pd.DataFrame]:
    """
    Retrieve all posts.

    Parameters
    ----------
    as_df : bool, optional
        If True, returns pandas DataFrame instead of query results
    """
    query = Post.select()
    if as_df:
        return pd.DataFrame(query.dicts())
    return query


def get_all_users(as_df: bool = True) -> Union[List[User], pd.DataFrame]:
    """
    Retrieve all users.

    Parameters
    ----------
    as_df : bool, optional
        If True, returns pandas DataFrame instead of query results
    """
    query = User.select()
    if as_df:
        return pd.DataFrame(query.dicts())
    return query


def get_user_by_name(
    username: str, as_df: bool = True
) -> Union[List[User], pd.DataFrame]:
    """
    Retrieve users by username.

    Parameters
    ----------
    username : str
        Username to search for
    as_df : bool, optional
        If True, returns pandas DataFrame instead of query results
    """
    query = User.select().where(User.username == username)
    if as_df:
        return pd.DataFrame(query.dicts())
    return query


# Schema management functions
def create_tables():
    with db:
        db.create_tables([User, Post])


# Initialize database
def initialize_database():
    db.connect()
    create_tables()
    db.close()


# Initialize database on module import
initialize_database()
