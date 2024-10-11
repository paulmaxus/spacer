from peewee import *
from datetime import datetime


# Database connection
db = SqliteDatabase('spacer.db')

# Base model class
class BaseModel(Model):
    class Meta:
        database = db

    @classmethod
    def create_or_update(cls, **kwargs):
        current_time = datetime.now()
        kwargs['last_updated'] = current_time

        cls.insert(**kwargs).on_conflict(
            conflict_target=[cls.id], update=kwargs
            ).execute()

# Models
class User(BaseModel):
    id = IntegerField(unique=True)
    username = CharField()
    role = CharField()
    join_date = DateTimeField()
    messages = IntegerField()
    reaction_score = IntegerField()
    points = IntegerField()
    last_updated = DateTimeField()

class Post(BaseModel):
    id = IntegerField(unique=True)
    user_id = ForeignKeyField(User, backref='posts')  # user.posts
    username = CharField()
    thread = CharField()
    message = TextField()
    likes = TextField() #IntegerField()
    time_posted = DateTimeField()
    last_updated = DateTimeField()

def get_posts_by_thread(thread):
    return Post.select().where(Post.thread == thread)
    
def get_user_by_name(username):
    # might be multiple
    return User.select().where(User.username == username)

def get_all_users():
    return User.select()

# Schema management functions
def create_tables():
    with db:
        db.create_tables([User, Post])

# Initialize database
def initialize_database():
    db.connect()
    create_tables()
    db.close()

initialize_database()