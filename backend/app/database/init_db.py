from app.database.base import Base
from app.database.session import engine
from app.models import user, classroom,folder,file

def init_db():
    Base.metadata.create_all(bind=engine)