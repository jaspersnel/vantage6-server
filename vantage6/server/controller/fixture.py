import logging
import inspect

from sqlalchemy import Table

import vantage6.server.model as db
from vantage6.server.model.base import Database

module_name = __name__.split('.')[-1]
log = logging.getLogger(module_name)

def load(fixtures, drop_all=False):
    if drop_all:
        Database().drop_all()

    session = Database().Session

    # Loop over all DB classes to see if they are in the fixtures yaml
    for name, cls in inspect.getmembers(db):

        # Any tables that inherit from db.Base
        if inspect.isclass(cls):
            if db.Base in inspect.getmro(cls):
                log.info(f'Adding {name} entries')

                for entry in fixtures.get(name, []):
                    session.add(cls(**entry))

        # Tables that are instances of sqlalchemy.Table
        elif isinstance(cls, Table):
            log.info(f'Adding {name} entries')
            table = cls

            for entry in fixtures.get(name, []):
                session.execute(table.insert().values(**entry))

    session.commit()
