# -*- coding: utf-8 -*-
# Standard library
import sys
import os
import logging
import datetime, time

import enum
import json
import bcrypt


#  SQLAlchemy
import sqlalchemy
from sqlalchemy import *
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import scoped_session, sessionmaker, relationship, backref
from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy.ext.orderinglist import ordering_list
from sqlalchemy.ext.hybrid import hybrid_property, hybrid_method
from sqlalchemy.ext.associationproxy import association_proxy



# ------------------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------------------
def init(URI='sqlite:////tmp/test.db', drop_all=False):
    """Initialize the database."""
    log = logging.getLogger(__name__)

    url = make_url(URI)
    log.info("Initializing the database")
    log.debug("  driver:   {}".format(url.drivername))
    log.debug("  host:     {}".format(url.host))
    log.debug("  port:     {}".format(url.port))
    log.debug("  database: {}".format(url.database))
    log.debug("  username: {}".format(url.username))

    import db
    db.URI = URI
    db.engine = create_engine(URI, convert_unicode=True)
    db.Session = scoped_session(sessionmaker(autocommit=False, autoflush=False))
    db.object_session = Session.object_session

    Session.configure(bind=db.engine)

    if drop_all:
        log.warn("Dropping existing tables!")
        Base.metadata.drop_all(db.engine)

    Base.metadata.create_all(bind=db.engine)
    log.info("Database initialized!")


def jsonable(value):
    """Convert a (list of) SQLAlchemy instance(s) to native Python objects."""
    if isinstance(value, list):
        return [jsonable(i) for i in value]

    elif isinstance(value, Base):
        retval = dict()
        mapper = inspect(value.__class__)

        columns = [c.key for c in mapper.columns if c.key not in value._hidden_attributes]

        for column in columns:
            column_value = getattr(value, column)

            if isinstance(column_value, enum.Enum):
                column_value = column_value.value
            elif isinstance(column_value, datetime.datetime):
                column_value = column_value.isoformat()

            retval[column] = column_value

        return retval

    # FIXME: does it make sense to raise an exception or should base types
    #        (or other JSON-serializable types) just be returned as-is?
    raise Exception('value should be instance of db.Base or list!')


def jsonify(value):
    """Convert a (list of) SQLAlchemy instance(s) to a JSON (string)."""
    return json.dumps(jsonable(value))


# ------------------------------------------------------------------------------
# Base declaration.
# ------------------------------------------------------------------------------
class Base(object):
    """Declarative base that defines default attributes."""
    _hidden_attributes = []

    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()
    
    # Primay key, internal use only
    id = Column(Integer, primary_key=True)

    @classmethod
    def get(cls, id_=None, with_session=False):
        session = Session()

        if id_ is None:
            result =  session.query(cls).all()    
        else:
            result = session.query(cls).filter_by(id=id_).one()

        if with_session:
            return result, session

        return result

    def save(self):
        if self.id is None:
            session = Session()
            session.add(self)
        else:
            session = object_session(self)

        session.commit()


Base = declarative_base(cls=Base)


# ------------------------------------------------------------------------------
# Real model/table definitions start here.
# ------------------------------------------------------------------------------
association_table_organization_collaboration = Table(
    'association_table_organization_collaboration', 
    Base.metadata,
    Column('organization_id', Integer, ForeignKey('organization.id')),
    Column('collaboration_id', Integer, ForeignKey('collaboration.id'))
)


# ------------------------------------------------------------------------------
class Organization(Base):
    """A legal entity."""
    name = Column(String)
    domain = Column(String)
    address1 = Column(String)
    address2 = Column(String)
    zipcode = Column(String)
    country = Column(String)



# ------------------------------------------------------------------------------
class Collaboration(Base):
    """Combination of 2 or more Organizations."""
    name = Column(String)

    organizations = relationship(
        'Organization', 
        secondary=association_table_organization_collaboration, 
        backref='collaborations'
    )


# ------------------------------------------------------------------------------
class Authenticatable(Base):
    """Yes, there is a typo in this class' name ;-)"""

    type = Column(String(50))
    ip = Column(String)
    last_seen = Column(DateTime)


    __mapper_args__ = {
        'polymorphic_identity':'authenticatable',
        'polymorphic_on': type,
    }


# ------------------------------------------------------------------------------
class User(Authenticatable):
    """User (person) that can access the system."""
    _hidden_attributes = ['password_hash']

    id = Column(Integer, ForeignKey('authenticatable.id'), primary_key=True)

    username = Column(String)    
    password_hash = Column(String)
    firstname = Column(String)
    lastname = Column(String)
    roles = Column(String)

    organization_id = Column(Integer, ForeignKey('organization.id'))
    organization = relationship('Organization', backref='users')

    __mapper_args__ = {
        'polymorphic_identity':'user',
    }


    # Copied from https://docs.pylonsproject.org/projects/pyramid/en/master/tutorials/wiki2/definingmodels.html
    def set_password(self, pw):
        pwhash = bcrypt.hashpw(pw.encode('utf8'), bcrypt.gensalt())
        self.password_hash = pwhash.decode('utf8')

    # Copied from https://docs.pylonsproject.org/projects/pyramid/en/master/tutorials/wiki2/definingmodels.html
    def check_password(self, pw):
        if self.password_hash is not None:
            expected_hash = self.password_hash.encode('utf8')
            return bcrypt.checkpw(pw.encode('utf8'), expected_hash)
        return False

    @classmethod
    def getByUsername(cls, username):
        session = Session()
        return session.query(cls).filter_by(username=username).one()



# ------------------------------------------------------------------------------
class Client(Authenticatable):
    """Application that executes Tasks."""
    _hidden_attributes = ['api_key']

    id = Column(Integer, ForeignKey('authenticatable.id'), primary_key=True)
    
    name = Column(String)
    api_key = Column(String)

    collaboration_id = Column(Integer, ForeignKey('collaboration.id'))
    collaboration = relationship('Collaboration', backref='clients')

    organization_id = Column(Integer, ForeignKey('organization.id'))
    organization = relationship('Organization', backref='clients')

    __mapper_args__ = {
        'polymorphic_identity':'client',
    }


    @classmethod
    def getByApiKey(cls, api_key):
        session = Session()
        return session.query(cls).filter_by(api_key=api_key).one()

    @property
    def open_tasks(self):
        # return [result for result in self.taskresults if result.finished_at is None]
        print(self.taskresults, type(self.taskresults))

        values = list()
        for r in self.taskresults:
            values.append(r)

        return values


# ------------------------------------------------------------------------------
class Task(Base):
    """Central definition of a single task."""
    name = Column(String)
    description = Column(String)
    image = Column(String)
    # status = Column(String)
    input = Column(Text)

    collaboration_id = Column(Integer, ForeignKey('collaboration.id'))
    collaboration = relationship('Collaboration', backref='tasks')

    @hybrid_property
    def complete(self):
        return all([r.finished_at for r in self.results])


# ------------------------------------------------------------------------------
class TaskResult(Base):
    """Result of a Task as executed by a Client.

    Unfinished TaskResults constitute a Client's todo list.
    """
    result =  Column(Text)

    assigned_at = Column(DateTime, default=datetime.datetime.utcnow)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    log = Column(Text)

    task_id = Column(Integer, ForeignKey('task.id'))
    task = relationship('Task', backref='results')

    client_id = Column(Integer, ForeignKey('client.id'))
    client = relationship('Client', backref='taskresults')

    @hybrid_property
    def isComplete(self):
        return self.finished_at is not None






