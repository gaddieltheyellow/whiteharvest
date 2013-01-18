#!/usr/bin/env python
from __future__ import division, print_function

import CairoPlot
import argparse
import collections
import datetime
import getpass
import json
import math
import operator
import os
import praw
import time
import random
import string
import sys


def write_db(db, db_file):
    f = open(db_file, 'w')
    json.dump(db, f, indent=2)
    f.close()


def ensure_username_password(username, password):
    if not username:
        username = raw_input('username: ')
    if not password:
        password = getpass.getpass('password: ')
    return username, password


def ensure_key_value(key, value):
    if key is None:
        key = raw_input('key:')
    if value is None:
        value = raw_input('value:')
    return key, value


def parse_comments(comments):
    ret = {}
    for obj in comments:
        if isinstance(obj, praw.objects.MoreComments):
            # This functionality seems to be broken in praw.  Whatevs
            #ret.update(parse_comments(obj.comments()))
            pass
        else:
            author = ''
            if obj.author:
                author = obj.author.name
            ret[obj.name] = {
                'author': author,
                'author_flair_css_class': obj.author_flair_css_class,
                'body': obj.body,
                'created_utc': obj.created_utc,
                'downs': obj.downs,
                'ups': obj.ups,
            }
    return ret


def update(username, password, db):
    # Create the reddit object
    characters = string.ascii_lowercase + string.ascii_uppercase + string.digits
    random_str = ''.join(random.choice(characters) for x in range(8))
    reddit = praw.Reddit(user_agent='whiteharvest-%s' % random_str)
    reddit.login(username, password)
    rChristianity = reddit.get_subreddit('Christianity')
        
    # only read in threads that:
    # * are at least a day old
    # * are newer than the oldest thread in the db
    #   (if the db is empty, only read one day's worth)
    a_day = 24 * 60 * 60
    max_timestamp = (time.time() + time.timezone) - a_day
    min_timestamp = max_timestamp - a_day
    if db['threads']:
        min_timestamp = max(x['created_utc'] for x in db['threads'].values())
    for thread in rChristianity.get_new_by_date(limit=None):
        if thread.created_utc >= max_timestamp:
            continue
        if thread.created_utc <= min_timestamp:
            break
        print('adding %s...' % thread.title)
        comments = parse_comments(thread.comments)
        author = ''
        if thread.author:
            author = thread.author.name
        db['threads'][thread.name] = {
            'author': author,
            'author_flair_css_class': thread.author_flair_css_class,
            'comments': comments,
            'created_utc': thread.created_utc,
            'downs': thread.downs,
            'selftext': thread.selftext,
            'title': thread.title,
            'ups': thread.ups,
        }
        yield db


def aligned_karma(db, user, flair, ups, downs):
    lower_users = dict((k.lower(), v) for k, v in db['users'].items())
    lower_flairs = dict((k.lower(), v) for k, v in db['flairs'].items())
    alignment = lower_users.get((user or '').lower())
    if alignment is None:
        if user is not None:
            print('Consider adding user', user, file=sys.stderr)
        alignment = lower_flairs.get((flair or '').lower())
    if alignment == 1:
        return (ups, downs)
    if alignment == -1:
        return (downs, ups)
    if alignment != 0 and flair is not None:
        print('Consider adding flair', flair, file=sys.stderr)
    return (0, 0)


def plot(db):
    alignments = collections.defaultdict(lambda: (0, 0))
    for thread in db['threads'].values():
        date = datetime.date.fromtimestamp(thread['created_utc'])
        alignment = aligned_karma(db, thread['author'],
                                  thread['author_flair_css_class'],
                                  thread['ups'], thread['downs'])
        alignments[date] = tuple(map(operator.add,
                                     alignments[date], alignment))
        for comment in thread['comments'].values():
            alignment = aligned_karma(db, comment['author'],
                                      comment['author_flair_css_class'],
                                      comment['ups'], comment['downs'])
            alignments[date] = tuple(map(operator.add,
                                         alignments[date], alignment))

    h_labels = []
    data = []
    for date, alignment in sorted(alignments.items()):
        h_labels.append(date.strftime('%Y-%m-%d'))
        # Should not need float here since we are using the __future__ division
        # but it seems we do anyway.
        percent = alignment[0] / sum(alignment)
        data.append((200 * percent) - 100)
    # Don't include the first or last day
    data = data[1:-1]
    h_labels = h_labels[1:-1]

    try:
        CairoPlot.dot_line_plot('rChristianity',
                                data,
                                width=800,
                                height=400,
                                background=None,
                                border=5,
                                axis=True,
                                grid=True,
                                dots=False,
                                h_labels=h_labels,
                                v_labels=None,
                                h_bounds=None,
                                v_bounds=(-100, 100))
    except ZeroDivisionError:
        print('CairoPlot is stupid and tried to divide by 0.', file=sys.stdout)
    else:
        print('rChristianity.svg created')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', help='[update|setuser|setflair|listusers|listflairs|plot]')
    parser.add_argument("--username",
                        help="your username")
    parser.add_argument("--password",
                        help="your password")
    parser.add_argument("--key",
                        help="a key")
    parser.add_argument("--value",
                        help="a value")
    args = parser.parse_args()

    home = os.path.expanduser('~')
    db_file = os.path.join(home, '.whiteharvest')

    db = {
        'threads': {},
        'users': {},
        'flair': {},
    }
    try:
        db = json.load(open(db_file))
    except OSError:
        pass
    except ValueError:
        print('Invalid json in dbfile')
        return -1

    if args.action == 'update':
        username, password = ensure_username_password(args.username,
                                                      args.password)
        count = 0
        for db in update(username, password, db):
            count += 1
            if count % 5 == 0:
                write_db(db, db_file)
        write_db(db, db_file)
    elif args.action == 'setuser':
        key, value = ensure_key_value(args.key, args.value)
        db['users'][key] = int(value)
        write_db(db, db_file)
    elif args.action == 'setflair':
        key, value = ensure_key_value(args.key, args.value)
        db['flairs'][key] = int(value)
        write_db(db, db_file)
    elif args.action == 'listusers':
        for user, value in sorted(db['users'].items()):
            print(user, value)
    elif args.action == 'listflairs':
        for flair, value in sorted(db['flairs'].items()):
            print(flair, value)
    elif args.action == 'plot':
        plot(db)
    else:
        parser.error('Not a valid action.')
        return -1

    return 0


if __name__ == '__main__':
    exit(main())
