#!/usr/bin/env python
"""
Analyze the alignment of r/Christianity
"""
from __future__ import division, print_function

# Headless hack
import matplotlib
matplotlib.use('Agg')

import argparse
import collections
import datetime
import getpass
import json
import netrc
import operator
import os
import praw
import pylab
import time
import random
import string
import sys


def write_db(data, db_file):
    f = open(db_file, 'w')
    json.dump(data, f, indent=2)
    f.close()


def write_threads(new_threads, old_threads, db_dir):
    date_map = collections.defaultdict(dict)
    for name, data in new_threads.items():
        if name not in old_threads:
            date = datetime.date.fromtimestamp(data['created_utc'])
            date_map[date][name] = data
    for date, data in date_map.items():
        date_str = date.strftime('%Y-%m-%d')
        db_file = os.path.join(db_dir, '%s.json' % date_str)
        try:
            db = json.load(open(db_file))
        except IOError:
            db = {}
        db.update(data)
        write_db(db, db_file)


def ensure_username_password(username, password):
    if not username and not password:
        try:
            hosts = netrc.netrc().hosts
        except netrc.NetrcParseError:
            pass
        else:
            default = None, None, None
            username, _, password = hosts.get('reddit.com', default)
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


def safe_string(text):
    try:
        str(text)
    except UnicodeEncodeError:
        return text.encode('ascii', 'ignore')
    return text


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

    threads = []
    for thread in rChristianity.get_new_by_date(limit=None):
        if thread.created_utc >= max_timestamp:
            continue
        if thread.created_utc <= min_timestamp:
            break
        threads.append(thread)

    print('%d thread(s) to read.' % len(threads))
    for thread in reversed(threads):
        title = safe_string(thread.title)
        print('adding %s...' % title)
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
            'title': title,
            'ups': thread.ups,
        }
        yield db


def aligned_karma(db, user, flair, ups, downs):
    lower_users = dict((k.lower(), v) for k, v in db['users'].items())
    lower_flairs = dict((k.lower(), v) for k, v in db['flairs'].items())
    alignment = lower_users.get((user or '').lower())
    if alignment is None:
        if user:
            print('Consider adding user', user, file=sys.stderr)
        alignment = lower_flairs.get((flair or '').lower())
    if alignment == 1:
        return (ups, downs)
    if alignment == -1:
        return (downs, ups)
    if alignment != 0 and flair:
        print('Consider adding flair', flair, file=sys.stderr)
    return (0, 0)


def plot_trend(date_map, filename):
    x_data = []
    y_data = []
    for date in sorted(date_map):
        data = date_map[date]
        x_data.append(date)
        y_data.append(data['total'])
        
    fig = pylab.figure(figsize=(9, 6), dpi=80, facecolor='#ffffff', edgecolor='#333333')
    fig.autofmt_xdate()
    pylab.grid(True)
    x_vals = pylab.np.array(list(range(len(x_data))))
    y_vals = pylab.np.array(y_data)
    pylab.plot(x_vals, y_vals, color='#555555', alpha=1.00)
    pylab.fill_between(x_vals, y_vals, 0, where=y_vals>0, color='#5555ff',
                       alpha=.25, interpolate=True)
    pylab.fill_between(x_vals, y_vals, 0, where=y_vals<0, color='#ff5555',
                       alpha=.25, interpolate=True)
    
    pylab.xlim(0, len(x_data) - 1)
    sep = int(len(x_vals) / 10)
    ran = list(range(0, len(x_vals), sep))
    pylab.xticks([x_vals[i] for i in ran], [x_data[i] for i in ran], rotation=45, ha='right')
    pylab.ylim(-100, 100)
    pylab.yticks(range(-100, 101, 25))
    pylab.text(len(x_vals) - 2, 87, '/r/Christianity alignment', ha='right',
               va='center', color="#333333", alpha=.55, fontsize=16)
    pylab.savefig(filename)


def split_color(color_str):
    r, g, b = color_str[1:3], color_str[3:5], color_str[5:7]
    return int('0x' + r, 0), int('0x' + g, 0), int('0x' + b, 0)


def create_color(r, g, b):
    r_str = hex(r).replace('x', '0')[-2:]
    g_str = hex(g).replace('x', '0')[-2:]
    b_str = hex(b).replace('x', '0')[-2:]
    return '#%s%s%s' % (r_str, g_str, b_str)


def spectrum(color1, color2, val):
    r1, g1, b1 = split_color(color1)
    r2, g2, b2 = split_color(color2)
    r = r1 + int((r2 - r1) * val)
    g = g1 + int((g2 - g1) * val)
    b = b1 + int((b2 - b1) * val)
    return create_color(r, g, b)


def plot_weekday(date_map, filename):
    blue = '#4213d1'
    red = '#d11320'
    x_data = []
    y_data = []
    c_data = []
    x_data_scaled = []
    y_data_scaled = []
    c_data_scaled = []
    y_ave = [[] for x in range(7)]
    c_ave = [0 for x in range(7)]
    norm_ave = [[] for x in range(7)]
    for data in date_map.values():
        x_data.append(data['weekday'])
        y_data.append(data['total'])
        c_data.append(spectrum(
                red, blue,
                float(data['total'] + 100) / 200))
        norm_ave[data['weekday']].append((data['total'] + 100) / 200)
        if 'scaled_weekday' in data:
            x_data_scaled.append(data['weekday'])
            y_data_scaled.append(data['scaled_weekday'])
            c_data_scaled.append(spectrum(
                    red, blue,
                    float(data['scaled_weekday'] + 100) / 200))
            y_ave[data['weekday']].append(data['scaled_weekday'])

    for i in range(7):
        norm_ave[i] = pylab.np.mean(norm_ave[i])
        y_ave[i] = pylab.np.mean(y_ave[i])
        c_ave[i] = spectrum(red, blue,
                            float(y_ave[i] + 100) / 200)

    pairs = [(val, key) for key, val in enumerate(norm_ave)]
    max_r_pair = max(pairs)
    min_r_pair = min(pairs)
    pairs = [(val, key) for key, val in enumerate(y_ave)]
    max_a_pair = max(pairs)
    min_a_pair = min(pairs)

    days = [
        'Sunday',
        'Monday',
        'Tuesday',
        'Wednesday',
        'Thursday',
        'Friday',
        'Saturday',
    ]
    diff = ('%0.0f%% more Christian\nthan %ss'
            % ((max_r_pair[0] / min_r_pair[0]) * 100, days[min_r_pair[1]]))
    fig = pylab.figure(figsize=(9, 6), dpi=80, facecolor='#ffffff', edgecolor='#333333')
    pylab.subplots_adjust(bottom=0.15)
    pylab.scatter(x_data, y_data, s=20, c=c_data, alpha=.5)
    pylab.scatter(x_data_scaled, y_data_scaled, s=75, c=c_data_scaled, alpha=.5)
    pylab.scatter(range(7), y_ave, s=300, c=c_ave, alpha=.7)
    pylab.grid(True)

    
    min_y_ave = min(y_ave)
    max_y_ave = max(y_ave)
    arrowprops=dict(arrowstyle="->",
                    connectionstyle="arc3,rad=-.3", facecolor='#333333',
                    edgecolor='#333333')
    pylab.annotate(diff, xy=(max_a_pair[1] - .07, max_a_pair[0] + 5),
                   color='#333333',
                   xytext=(.5, 55), ha='center',
                   fontsize=12, 
                   arrowprops=arrowprops)
    
    pylab.xlim(-1, 7)
    pylab.xticks(range(7), days, rotation=45, ha='right')
    pylab.ylim(-100, 100)
    pylab.yticks(range(-100, 101, 25))
    pylab.text(6.5, 87, '/r/Christianity alignment', ha='right',
               va='center', color="#333333", alpha=.55, fontsize=16)
    pylab.savefig(filename)


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
            date = datetime.date.fromtimestamp(comment['created_utc'])
            alignment = aligned_karma(db, comment['author'],
                                      comment['author_flair_css_class'],
                                      comment['ups'], comment['downs'])
            alignments[date] = tuple(map(operator.add,
                                         alignments[date], alignment))

    # Don't include the first or last day
    del alignments[max(alignments)]
    del alignments[min(alignments)]

    h_labels = []
    data = []
    date_map = {}
    week_map = collections.defaultdict(list)
    for date, alignment in sorted(alignments.items()):
        percent = alignment[0] / sum(alignment)
        total = (200 * percent) - 100
        weekday = (date.weekday() + 1) % 7
        sunday = date - datetime.timedelta(days=weekday)
        date_map[date.strftime('%Y-%m-%d')] = {
            'total': total,
            'weekday': weekday,
        }
        week_map[sunday.strftime('%Y-%m-%d')].append(total)
    for date, alignment in sorted(alignments.items()):
        weekday = (date.weekday() + 1) % 7
        sunday = date - datetime.timedelta(days=weekday)
        week = week_map[sunday.strftime('%Y-%m-%d')]
        if len(week) < 4:
            continue
        max_align = max(week)
        min_align = min(week)
        diff = max_align - min_align
        total = date_map[date.strftime('%Y-%m-%d')]['total']
        percent = .5
        if diff != 0:
            percent = float(total - min_align) / diff
        scaled_weekday = (200 * percent) - 100
        date_map[date.strftime('%Y-%m-%d')]['scaled_weekday'] = scaled_weekday
    plot_trend(date_map, 'trend.png')
    plot_weekday(date_map, 'weekday.png')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', help='[update|setuser|setflair|'
                                       'listusers|listflairs|plot]')
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
    db_dir = os.path.join(home, '.whiteharvest')
    user_file = os.path.join(db_dir, 'users.json')
    flair_file = os.path.join(db_dir, 'flairs.json')

    # TODO: don't always load up the whole db
    db = {
        'threads': {},
        'users': {},
        'flair': {},
    }
    try:
        db['users'] = json.load(open(user_file))
        db['flairs'] = json.load(open(flair_file))
        for filename in os.listdir(db_dir):
            data = json.load(open(os.path.join(db_dir, filename)))
            if filename == 'users.json':
                db['users'] = data
            elif filename == 'flairs.json':
                db['flairs'] = data
            else:
                db['threads'].update(data)
    except OSError:
        pass
    except ValueError:
        print('Invalid json in dbfile')
        return -1

    if args.action == 'update':
        username, password = ensure_username_password(args.username,
                                                      args.password)
        old_threads = dict(db['threads'])
        for i, db in enumerate(update(username, password, db)):
            if i % 10 == 0:
                write_threads(db['threads'], old_threads, db_dir)
                old_threads = dict(db['threads'])
        write_threads(db['threads'], old_threads, db_dir)
    elif args.action == 'setuser':
        key, value = ensure_key_value(args.key, args.value)
        db['users'][key] = int(value)
        write_db(db['users'], user_file)
    elif args.action == 'setflair':
        key, value = ensure_key_value(args.key, args.value)
        db['flairs'][key] = int(value)
        write_db(db['flairs'], flair_file)
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
