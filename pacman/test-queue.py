#!/usr/bin/env python

from flask import Flask, request
import threading, queue
import sqlite3
from typing import Dict, Tuple
import pandas as pd
import logging
import tempfile

app = Flask(__name__)
q = queue.Queue()

@app.route('/log', methods=['POST'])
def log() -> Tuple[str, int]:
    """ Add valid JSON requests to the queue """

    if request.is_json:
        q.put(request.get_json())
        return 'OK', 200
    else:
        return 'Must be JSON :(', 400

def logging_worker(barrier):
    """ Start logging nextflow data via HTTP web logs.

    The default Flask HTTP server is only suitable for deployment in internal
    firewalled places, with low loads. Please don't use on the public Internet.
    """
    barrier.wait()
    app.run(threaded=False)

def sqlite_worker(db, barrier):
    """ Store JSON logs in a sqlite database.

    Hopefully blocking and transactions will avoid a race condition. """
    barrier.wait()
    con: sqlite3.Connection = sqlite3.connect(db)
    cur = con.cursor()
    cur.execute(''' CREATE TABLE IF NOT EXISTS logs
        (runName text, runId text, event text, utcTime text) ''')
    con.commit()

    while True:
        item = q.get()
        cur.execute("INSERT INTO logs VALUES (:runName, :runId, :event, :utcTime)", item)
        con.commit()
        q.task_done()

def status_worker(db, event_start, event_complete):
    """ Monitor the database for pipeline progress """

    con: sqlite3.Connection = sqlite3.connect(db)

    while True:
        if not event_complete.wait(1): # wait blocks, timeout checks 1 per sec
            df = pd.read_sql('SELECT * from logs', con)
            started = df.query('event == "started"')
            completed = df.query('event == "completed"')

            assert started.shape[0] <= 1, "Duplicated start logs in DB"
            assert completed.shape[0] <= 1, "Duplicated complete logs in DB"

            if not started.empty and not event_start.isSet():
                logging.debug('Pipeline started')
                event_start.set()

            if not completed.empty:
                logging.debug('Pipeline completed')
                event_complete.set()

def clear_db(db, event_start, event_complete):
    """ Clear the database ready for logs from a new pipeline job """
    while True:
        if event_complete.wait(1):
            q.join() # block the queue - wait until it's empty
            con: sqlite3.Connection = sqlite3.connect(db)
            cur = con.cursor()
            cur.execute("DELETE FROM logs") # drop all rows
            con.commit()
            con.close()
            logging.debug('Job complete, local database cleared')
            event_start.clear()
            event_complete.clear()

def main():
    """ Doesn't support concurrent nextflow weblogs """
    logging.basicConfig(level=logging.DEBUG,
                    format='(%(threadName)-9s) %(message)s',)
    db = tempfile.NamedTemporaryFile(delete=False)
    logging.debug('SQLite database: {}'.format(db.name))

    barrier = threading.Barrier(2)
    event_start = threading.Event()
    event_complete = threading.Event()
    threading.Thread(target = logging_worker, args = (barrier,), daemon=True).start()
    threading.Thread(target = sqlite_worker, args = (db.name,barrier), daemon=True).start()
    threading.Thread(target = status_worker, args = (db.name, event_start, event_complete)).start()
    threading.Thread(target = clear_db, args = (db.name, event_start, event_complete)).start()


if __name__ == "__main__":
    main()
