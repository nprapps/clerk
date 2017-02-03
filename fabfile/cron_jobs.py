#!/usr/bin/env python

"""
Cron jobs
"""
import json
import logging
import os
import requests

from datetime import datetime
from fabric.api import local, require, task
from lxml import etree
from pyquery import PyQuery as pq


import app_config

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

TIMESTAMP_STORAGE_FILE = 'data/house-timestamp.txt'
WEBHOOK = app_config.get_secrets()['WEBHOOK']
URL = 'http://clerk.house.gov/floorsummary/Download.aspx?file={0}.xml'

@task
def post_message():
    actions = get_new_actions()
    if len(actions['attachments']) > 0:
        r = requests.post(WEBHOOK, data=json.dumps(actions))
        logger.info(r.text)
    else:
        logger.info('No new action')


def get_new_actions():
    today = datetime.now().strftime('%Y%m%d')
    xml_parser = etree.XMLParser(ns_clean=True, recover=True, encoding='utf-8')
    html_parser = etree.HTMLParser(encoding='utf-8')

    r = requests.get(URL.format(today))
    xml = r.text.encode('utf-8')
    d = pq(etree.fromstring(xml, parser=xml_parser))
    actions = d('floor_action')

    last_timestamp = get_timestamp()
    timestamp_logged = False
    attachments = []

    for action in actions:
        data = {}
        
        # handle action time
        timestamp = action.find('action_time').values()[0]
        full_datetime = datetime.strptime(timestamp, '%Y%m%dT%H:%M:%S')
        if last_timestamp and (full_datetime <= last_timestamp):
            break

        if not timestamp_logged:
            log_timestamp(timestamp)
            timestamp_logged = True

        data['time'] = full_datetime.strftime('%I:%M')

        # handle action item
        if action.find('action_item') is not None:
            data['item'] = action.findtext('action_item')

        # handle action description by parsing as HTML
        string_desc = etree.tostring(action.find('action_description'))
        h = pq(etree.fromstring(string_desc, parser=html_parser))
        data['desc'] = h.text()

        attachment = build_attachment(data)
        attachments.append(attachment)

    return {
        'text': 'New action in the House',
        'attachments': attachments
    }


def get_timestamp():
    if os.path.exists(TIMESTAMP_STORAGE_FILE):
        with open(TIMESTAMP_STORAGE_FILE) as f:
            timestamp = f.read()
            return datetime.strptime(timestamp, '%Y%m%dT%H:%M:%S')
    else:
        return None


def log_timestamp(timestamp):
    with open(TIMESTAMP_STORAGE_FILE, 'w') as f:
        f.write(timestamp)


def build_attachment(data):
    return {
        'fallback': data['desc'],
        'author_name': data['time'],
        'title': data.get('item', ''),
        'title_link': build_bill_link(data['item']) if data.get('item') else '',
        'text': data['desc']
    }


def build_bill_link(item):
    base_url = 'https://www.congress.gov/{0}/115th-congress/{1}/{2}'
    number = item.split('. ')[-1]

    if item.startswith('H.R.'):
        return base_url.format('bill', 'house-bill', number)
    elif item.startswith('S.'):
        return base_url.format('senate-bill', number)
    elif item.startswith('H. Amdt.'):
        return base_url.format('amendment', 'house-amendment', number)
    elif item.startswith('S. Amdt.'):
        return base_url.format('amendment', 'senate-amendment', number)
    elif item.startswith('H. Res.'):
        return base_url.format('bill', 'house-resolution', number)
    elif item.startswith('H. Res.'):
        return base_url.format('bill', 'senate-resolution', number)
    elif item.startswith('H.J. Res.'):
        return base_url.format('bill', 'house-joint-resolution', number)
    elif item.startswith('S.J. Res.'):
        return base_url.format('bill', 'senate-joint-resolution', number)
    elif item.startswith('H.J. Res.'):
        return base_url.format('bill', 'house-joint-resolution', number)
    elif item.startswith('H. Con. Res.'):
        return base_url.format('bill', 'house-concurrent-resolution', number)
    elif item.startswith('S. Con. Res.'):
        return base_url.format('bill', 'senate-concurrent-resolution', number)