from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, id, user_type):
        self.id = id
        self.user_type = user_type
